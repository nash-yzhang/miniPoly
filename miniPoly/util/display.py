import numpy as np
from importlib import util
import sys
from time import perf_counter as _perf_counter

from vispy import gloo, app

from miniPoly.core.minion import AbstractMinionMixin

_default_plane_VS = """
    #version 130
    attribute vec2 a_pos;
    varying vec2 v_pos;
    void main () {
        v_pos = a_pos;
        gl_Position = vec4(a_pos, 0.0, 1.0);
    }
    """

_default_plane_FS = """
    uniform float u_time;
    void main() {
        gl_FragColor = vec4(vec3(sin(u_time),cos(u_time),sin(u_time+1.57/2))/2.+.5, 1.);
    }
    """

DEFAULT_SPHERE_VS = """
    #version 130
    attribute vec3 a_pos;
    varying vec3 v_pos;
    uniform mat4 u_view;
    uniform mat4 u_model;
    uniform mat4 u_projection;
    void main () {
        v_pos = a_pos;
        gl_Position = u_projection * u_view * u_model * vec4(a_pos, 1.0);
    }
    """

DEFAULT_SPHERE_FS = """
    uniform float u_time;
    void main() {
        gl_FragColor = vec4(vec3(sin(u_time),cos(u_time),sin(u_time+1.57/2))/2.+.5, 1.);
    }
    """


def _load_module_from_path(path, module_prefix):
    """Load a Python module from a file without changing sys.path."""
    normalized = str(path)
    module_stem = normalized.replace("\\", "/").rsplit("/", 1)[-1].rsplit(".", 1)[0]
    module_name = f"{module_prefix}_{module_stem}"
    spec = util.spec_from_file_location(module_name, location=normalized)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not create a module spec for {normalized}")
    module = util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class GLDisplay(app.Canvas, AbstractMinionMixin):
    """Dynamically load and run ``Renderer(canvas)`` scripts."""

    def __init__(self, handler, *args, controllerProcName=None, **kwargs):
        """Set up the canvas in its no-renderer-loaded state and start its draw/FPS timer.

        Draws a black placeholder (`_draw_placeholder`) until `load()` swaps in a real
        renderer's `on_draw`; the timer starts immediately so `on_timer` begins polling
        `handler` and the controller minion right away, independent of when a renderer
        script actually arrives.
        """
        app.Canvas.__init__(self, *args, **kwargs)
        self._processHandler = handler
        self._controllerProcName = controllerProcName
        self._renderer = None
        self._renderer_path = None
        self._draw_callback = self._draw_placeholder
        self._resize_callback = None
        self._canvas_closed = False
        self._render_suspended = False
        self._fps_enabled = False
        self._fps_interval = 1.0
        self._fps_window_started = _perf_counter()
        self._fps_frame_count = 0
        self._measured_fps = 0.0

        self.timer = app.Timer("auto", self.on_timer, start=True, app=self.app)
        self.events.draw.connect(self._draw_callback)
        self.events.draw.connect(self._record_frame)
        self.events.close.connect(self._handle_canvas_close)

    @property
    def controllerProcName(self):
        """Return the name of the minion whose messages this canvas listens to."""
        return self._controllerProcName

    @controllerProcName.setter
    def controllerProcName(self, value):
        """Set the name of the controller minion this canvas polls for messages."""
        self._controllerProcName = value

    @property
    def renderer(self):
        """Return the active renderer instance, or None before one is loaded."""
        return self._renderer

    @property
    def measured_fps(self):
        """Return the most recent draw-event frame-rate measurement."""
        return self._measured_fps

    def load(self, renderer):
        """Swap in `renderer` as the active draw/resize handler, replacing whatever was loaded before.

        Disconnects the previous draw (and, if present, resize) callback before wiring
        up the new one, so this is safe to call repeatedly -- that's what makes
        hot-swapping renderer scripts at runtime (the "rendering_script" branch of
        `parse_msg`) possible without leaking duplicate VisPy event-handler
        connections. `renderer.init_renderer()` runs after the new callbacks are wired
        but before `self._renderer` is updated, so a renderer's `init_renderer` can
        assume its own `on_draw`/`on_resize` are already live.
        """
        self.events.draw.disconnect(self._draw_callback)
        if self._resize_callback is not None:
            self.events.resize.disconnect(self._resize_callback)

        self.VS = renderer.VS
        self.FS = renderer.FS
        self.program = renderer.program
        self._draw_callback = renderer.on_draw
        self._resize_callback = getattr(renderer, "on_resize", None)
        self.events.draw.connect(self._draw_callback)
        if self._resize_callback is not None:
            self.events.resize.connect(self._resize_callback)
        renderer.init_renderer()
        self._renderer = renderer
        self.update()

    def parse_msg(self, msg_type, msg):
        """Dispatch an inbound IPC message from the controller minion by its `msg_type`.

        Handles the message kinds the GUI side (`miniPoly/util/gui.py`) and controller
        can send: a new renderer script to hot-load (`rendering_script`), a replacement
        fragment shader for the currently loaded renderer (`rendering_shader`, ignored
        if no renderer is loaded yet), a suspend/restart command (`display_control`),
        and FPS-logging config (`display_debug`). Unknown `msg_type`s are silently
        ignored.
        """
        if msg_type == "rendering_script":
            self.rendererScriptName = str(msg)
            self._processHandler.info(
                "Received rendering script [{}] from [{}]".format(
                    self.rendererScriptName,
                    self.controllerProcName,
                )
            )
            self.importModuleFromPath()
            self._renderer = self.imported.Renderer(self)
            self.load(self._renderer)
            self._processHandler.info("Running script [{}]".format(self.rendererScriptName))
        elif msg_type == "rendering_shader" and self._renderer is not None:
            try:
                self._renderer.reload(msg)
            except Exception as exc:
                self._processHandler.error(
                    "Could not reload the active fragment shader: {}".format(exc)
                )
        elif msg_type == "display_control":
            self.control_display(msg)
        elif msg_type == "display_debug":
            self.configure_debug(msg)

    def on_timer(self, event):
        """Per-tick driver: watch for a shutdown request, drain inbound messages, and redraw.

        Runs off `self.timer` (started in `__init__`). A non-positive `status` on the
        owning minion means a shutdown was requested elsewhere, so this closes the
        canvas instead of continuing to tick. Otherwise it pulls any pending message
        from the controller minion (dispatched via `parse_msg`), triggers a redraw
        unless rendering is suspended, and rolls over the FPS measurement.
        """
        if self._processHandler.status <= 0:
            self.on_close()
            return
        if self.controllerProcName is not None:
            self.get_nowait(self.controllerProcName)
        if not self._render_suspended:
            self.update()
        self._publish_fps_if_due()

    def _record_frame(self, event):
        """Count a completed draw event toward the current FPS measurement window."""
        self._fps_frame_count += 1

    def _publish_fps_if_due(self):
        """Roll over the FPS measurement window once `_fps_interval` seconds have elapsed.

        Called every tick from `on_timer` but only does work once per window:
        recomputes `_measured_fps` from the frame count accumulated by `_record_frame`,
        resets the counter, and -- only if FPS logging was turned on via
        `configure_debug` -- logs the result.
        """
        now = _perf_counter()
        elapsed = now - self._fps_window_started
        if elapsed < self._fps_interval:
            return
        self._measured_fps = self._fps_frame_count / elapsed
        self._fps_frame_count = 0
        self._fps_window_started = now
        if self._fps_enabled:
            self._processHandler.info(
                "Actual renderer FPS: {:.2f}".format(self._measured_fps)
            )

    def configure_debug(self, config):
        """Configure optional display diagnostics sent by the GUI."""
        if isinstance(config, dict):
            self._fps_enabled = bool(config.get("fps_enabled", False))
            interval = config.get("fps_interval", self._fps_interval)
            self._fps_interval = max(0.1, float(interval))
        else:
            self._fps_enabled = bool(config)
        self._fps_window_started = _perf_counter()
        self._fps_frame_count = 0
        state = "enabled" if self._fps_enabled else "disabled"
        self._processHandler.info(
            "Actual FPS logging {} (interval: {:.2f}s)".format(
                state,
                self._fps_interval,
            )
        )

    def _draw_placeholder(self, event):
        """Default draw callback before any renderer script is loaded: just clear to black."""
        gloo.clear("black")

    def control_display(self, command):
        """Apply a "suspend"/"restart" command from the controller: hide/pause or show/resume rendering."""
        if command == "suspend":
            self._render_suspended = True
            self.show(False)
        elif command == "restart":
            self._render_suspended = False
            self.show(True)
            self.update()

    def _handle_canvas_close(self, event):
        """Handle the canvas's own close event (e.g. the user closed the window directly).

        Stops the timer and, if the owning minion hasn't already been told to shut down
        (`status > 0`), triggers `shutdown()` so closing the window also tears down the
        minion rather than leaving it running with a dead canvas.
        """
        self._canvas_closed = True
        if self.timer.running:
            self.timer.stop()
        if self._processHandler.status > 0:
            self._processHandler.info("Renderer canvas closed")
            self.shutdown()

    def on_close(self):
        """Tear down the canvas from the minion side: stop the timer and close the window if not already closed.

        Called by `on_timer` when the owning minion's status indicates shutdown;
        guards against double-closing if `_handle_canvas_close` (the canvas's own close
        event) already ran.
        """
        if self.timer.running:
            self.timer.stop()
        if not self._canvas_closed:
            self.close()

    def importModuleFromPath(self):
        """Import `self.rendererScriptName` as the active renderer module via `_load_module_from_path`."""
        self.imported = _load_module_from_path(
            self.rendererScriptName,
            "minipoly_display_renderer",
        )


class GLRenderer:
    """Default point/grid renderer used as a fallback when no custom renderer script is loaded."""

    def __init__(self, canvas):
        """Compile the default vertex/fragment shaders and GL programs for `canvas`."""

        self.canvas = canvas
        self.VS = """
            #version 130
            attribute vec2 a_pos;
            varying vec2 v_pos;
            void main () {
                v_pos = a_pos;
                gl_PointSize = 10.;
                gl_Position = vec4(a_pos, 0.0, 1.0);
            }
            """

        self.FS = """
            varying vec2 v_pos; 
            uniform float u_alpha; 
            uniform float u_time; 
            void main() {
                float marker = step(.5,distance(gl_PointCoord,vec2(.5)));
                float color = sin(v_pos.x*20.+u_time*30.)/2.-.15+marker;
                gl_FragColor = vec4(vec3(color), u_alpha);
            }
        """
        self.FS2 = """
            varying vec2 v_pos; 
            void main() {
             float color = min(step(abs(v_pos.x),.97),step(abs(v_pos.y),.965));
             gl_FragColor = vec4(vec3(color), .5); }
        """
        self.program = gloo.Program(self.VS, self.FS)
        self.bg = gloo.Program(self.VS, self.FS)

    def init_renderer(self):
        """Bind the full-viewport quad and initial uniforms; called once this renderer is loaded onto a canvas."""
        self.program['a_pos'] = np.array([[-1., -1.], [-1., 1.], [1., -1.], [1., 1.]], np.float32)  # /2.
        self.program['u_time'] = 0
        self.program['u_alpha'] = np.float32(1)
        gloo.set_state("translucent")
        self.program['u_resolution'] = (self.canvas.size[0], self.canvas.size[1])

    def reload(self, fragment_shader):
        """Replace the fragment shader while preserving the renderer type."""
        previous_shader = self.FS
        previous_program = self.program
        self.FS = fragment_shader
        self.program = gloo.Program(self.VS, self.FS)
        try:
            self.init_renderer()
        except Exception:
            self.FS = previous_shader
            self.program = previous_program
            raise
        self.canvas.FS = self.FS
        self.canvas.program = self.program
        self.canvas.update()

    def on_draw(self, event):
        """Clear the canvas and draw the shader-animated quad, driven by the canvas's own elapsed time."""
        gloo.clear('white')
        u_time = self.canvas.timer.elapsed
        self.program['u_time'] = u_time
        self.program.draw('triangle_strip')

    def on_resize(self, event):
        """Resize the GL viewport and update the resolution uniform to match the canvas's new size."""
        gloo.set_viewport(0, 0, *self.canvas.physical_size)
        self.program['u_resolution'] = (self.canvas.size[0],self.canvas.size[1])
