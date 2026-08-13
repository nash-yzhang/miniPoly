import traceback
from time import sleep, time

import numpy as np
import pandas as pd
from PyQt5 import QtWidgets as qw, QtCore as qc
from PyQt5.QtGui import QIcon, QPixmap
from vispy import app, gloo

from miniPoly.compiler.prototypes import AbstractCompiler
from miniPoly.core.minion import AbstractMinionMixin, BaseMinion
from miniPoly.definition import ROOT_DIR
from miniPoly.compiler.prototypes import StreamingCompiler

import cv2
# Underscore alias keeps `contract` out of this module's public namespace.
from miniPoly.core import contract as _contract

def resize_with_padding(image_array, target_width, target_height, padding_color=(0, 0, 0)):
    """Letterbox `image_array` into a `target_width` x `target_height` canvas, preserving aspect ratio.

    Scales to fit without cropping, then centers the result on a solid `padding_color`
    background -- used to fit an arbitrary camera/shader frame into a fixed-size preview
    buffer without distorting it.
    """
    # Calculate the ratio and determine new dimensions
    original_height, original_width = image_array.shape[:2]
    ratio = min(target_width / original_width, target_height / original_height)
    new_width = int(original_width * ratio)
    new_height = int(original_height * ratio)

    # Resize the image
    resized_img = cv2.resize(image_array, (new_width, new_height), interpolation=cv2.INTER_NEAREST)

    # Create a new image with the target size and padding color
    padded_image = np.full((target_height, target_width, 3), padding_color, dtype=np.uint8)

    # Calculate padding offsets
    x_offset = (target_width - new_width) // 2
    y_offset = (target_height - new_height) // 2

    # Place the resized image onto the new image (centered)
    padded_image[y_offset:y_offset+new_height, x_offset:x_offset+new_width] = resized_img

    return padded_image

class QtCompiler(AbstractCompiler, qw.QMainWindow):
    """A minimal Qt-window compiler: opens the process's main window and shows a splash screen.

    Multiply inherits from AbstractCompiler and QMainWindow so a single instance is both a
    minion-side compiler (ticked by `_on_time`) and a real Qt widget; unlike ShaderStreamer,
    it adds no rendering or streaming of its own -- subclasses that need a plain Qt window
    without vispy's OpenGL canvas build on this instead.
    """

    def __init__(self, processHandler, **kwargs):
        """Initialize both parent classes and show the splash screen while the window comes up.

        Both `AbstractCompiler.__init__` and `qw.QMainWindow.__init__` are called explicitly
        rather than through `super()`, since this is a diamond of two unrelated base classes
        and only one of them (QMainWindow) takes the `**kwargs`.
        """
        AbstractCompiler.__init__(self, processHandler)
        qw.QMainWindow.__init__(self, **kwargs)
        self.setWindowTitle(self.name)
        self.setWindowIcon(QIcon(ROOT_DIR + '/minipoly.ico'))
        self.renderSplashScreen()

    def renderSplashScreen(self):
        """Show the miniPoly icon as a splash screen with a brief fade-in/out.

        Purely cosmetic, run once from `__init__`; the fixed 20-step loop with
        `sleep(0.03)` blocks for about 0.6s while the window is constructed.
        """
        splash_pix = QPixmap(ROOT_DIR + '/minipoly.ico')
        splash = qw.QSplashScreen(splash_pix, qc.Qt.WindowStaysOnTopHint)
        # add fade to splashscreen
        splash.show()
        for i in range(20):
            splash.setWindowOpacity(1.5 - abs(1.5 - (i / 10)))
            sleep(0.03)
        splash.close()  # close the splash screen


class ShaderStreamer(app.Canvas, StreamingCompiler):
    """A vispy GL canvas that renders a fragment shader and can stream its uniforms/protocol to disk.

    Combines `vispy.app.Canvas` (the OpenGL window and its `on_draw`/`on_resize`/`on_close`
    event hooks) with `StreamingCompiler` (the state/buffer streaming lifecycle from
    prototypes.py). A shader's uniforms become streaming states automatically (see
    `create_shared_uniform_state`), and a protocol table -- an Excel file whose columns are
    uniform names and whose PROTOCOL_TIME_COLUMN gives each row's onset time -- can drive
    those uniforms over a run (see `_start_protocol`/`_run_protocol`/`_end_protocol`).
    Rendering always happens into an off-screen framebuffer (`_fbo`) sized `max_frame_shape`,
    whose contents are published as the APP_FBO_PREVIEW shared buffer every frame,
    independent of the on-screen window's own size.
    """

    _vpos = np.array([[-1, -1], [+1, -1], [-1, +1], [+1, +1]], dtype=np.float32)

    VS = """
    attribute vec2 a_position;
    varying vec2 v_position;
    void main (void) {
        gl_Position = vec4(a_position, 0.0, 1.0);
        v_position = a_position;
    }
    """

    def __init__(self, processHandler, *args, FSFn=None, fullscreen=False, timer_minion=None, trigger_minion=None,
                 max_frame_shape=(1920,1080), **kwargs):
        """
        :param max_frame_shape: shape of the render target, in **numpy/vispy order
            (rows, columns) = (height, width)** -- not (width, height).

            This parameter used to be called `max_screen_size`, which read as a screen
            size and therefore as (W, H). It is not: it goes straight into
            `gloo.Texture2D`, `gloo.RenderBuffer` (whose own docstring says "shape in yx
            order") and `np.zeros`, all of which take rows first, and `FrameBuffer.read()`
            hands back `(h, w, c)` to match. The one caller,
            `CaImg_App/app_setter/visual_testing.py`, already passes `(480, 800)`
            alongside a `size=(800, 480)` canvas, i.e. it had worked the order out and
            swapped by hand. Renaming is behaviour-preserving; it only stops the next
            reader from having to.

            Note the default `(1920, 1080)` is portrait under this order. It is left as
            it was because changing a default is not behaviour-preserving and no caller
            relies on it.
        """
        # timer_minion / trigger_minion used to default to 'SCAN' / 'GUI', i.e. one
        # particular application's minion names were baked in as library defaults.
        # They are now None and callers must be explicit.
        # (The only call site, CaImg_App/app_setter/visual_testing.py, already passed
        #  both explicitly, so the defaults never took effect and this is behaviour
        #  preserving.)
        super().__init__(*args, **kwargs)
        StreamingCompiler.__init__(self, processHandler, timer_minion=timer_minion,
                                   trigger_minion=trigger_minion)  # self.VS = None
        self.FS = None
        self.program = None
        self._shared_uniform_states = []

        if FSFn is not None:
            self._FSFn = FSFn
            self._init_program()
        else:
            self._FSFn = ''

        self.create_streaming_state(_contract.APP_SHADER_FILE, self._FSFn, shared=False, use_buffer=False)
        self.watch_state(_contract.APP_SHADER_FILE, self._FSFn)

        self.fullscreen = fullscreen
        self.watch_state(_contract.APP_FULLSCREEN, self.fullscreen)

        # (rows, columns); see the max_frame_shape docstring above. Texture2D,
        # RenderBuffer, the preview buffer and FrameBuffer.read() all agree on this order,
        # which is why no transpose is needed anywhere on this path.
        self._max_frame_shape = max_frame_shape
        # Create texture to render to
        self._rendertex = gloo.Texture2D((*self._max_frame_shape, 3))
        # Create FBO, attach the color buffer and depth buffer
        self._fbo = gloo.FrameBuffer(color=self._rendertex, depth=gloo.RenderBuffer(self._max_frame_shape))
        self._frame_delta = time()

        self.create_shared_buffer(_contract.APP_FBO_PREVIEW, np.zeros((*self._max_frame_shape, 3), dtype=np.uint8))


        # Protocol execution related params
        self.watch_state(_contract.PROTOCOL_RUN, False)  # create a runSignal watcher, runSignal is a shared state from GUI

        self.create_streaming_state(_contract.PROTOCOL_FILE, '', shared=False, use_buffer=False)
        self.watch_state(_contract.PROTOCOL_FILE, '')

        self.watch_state(_contract.PROTOCOL_CMD_INDEX, -1)
        self.create_streaming_state(_contract.PROTOCOL_CMD_INDEX, -1, shared=True, use_buffer=True)
        self._protocolFn = ''
        self._protocol = None
        self._protocol_start_time = None
        self._time_index_col = None
        self._running_time = 0

    def load_shader_file(self, fn):
        """Read a shader source file from disk and return its text.

        Raises whatever `open`/`read` raises; `load_FS` is the only caller and is where I/O
        errors are actually caught and logged.
        """
        with open(fn, 'r') as shaderfile:
            return (shaderfile.read())

    def load_FS(self, fn):
        """Load a fragment shader file, or return None and log the error if it cannot be read.

        Only wraps `load_shader_file`'s exceptions; the returned text is not otherwise
        validated as GLSL until `_init_program` hands it to `gloo.Program`.
        """
        try:
            FS = self.load_shader_file(fn)
            return FS
        except Exception:
            self.error(f'Error in loading vertex shader: {fn}\n{traceback.format_exc()}')
            return None

    def _init_program(self):
        """(Re)build the GL program from `self._FSFn` and re-derive its shared uniform states.

        Called once at construction (if `FSFn` was given) and again from `get_FS` whenever
        the trigger minion pushes a new shader file. Drops any previously shared uniform
        states first (`remove_shared_uniform_state`) since the old shader's uniforms may not
        exist in the new one, then rebuilds them from the freshly compiled program's
        `variables`. Logs, rather than raises, when `self.FS` failed to load -- `self.program`
        is simply left `None` in that case, and `on_time`/`on_draw` already treat a `None`
        program as "nothing to render yet".
        """
        self.FS = self.load_FS(self._FSFn)
        # if self.VS is not None and self.FS is not None:
        if self.FS is not None:
            self.remove_shared_uniform_state()
            self.program = gloo.Program(self.VS, self.FS)
            self.program['a_position'] = gloo.VertexBuffer(self._vpos)
            self.program['u_resolution'] = (self.size[0], self.size[1])
            self.program['u_time'] = 0
            self.create_shared_uniform_state(type='uniform')
            rv, uv = self.check_variables()
            if uv:
                self.warning(f'Found {len(uv)} unsettled variables: {uv}')
                for i in uv:
                    self.program[i] = self.get_streaming_state(i)  # Set the uniform to the value in the streaming state
            if rv:
                self.warning(f'Found {len(rv)} pending variables: {rv}')
        else:
            self.error(f'Rendering program has not been built!')

    def create_shared_uniform_state(self, type='uniform'):
        """Register one streaming state per shader uniform of `type`, so it can be protocol-driven.

        Called from `_init_program` after a (re)build. Skips `u_resolution`/`u_time`, which
        are driven internally every frame, not by protocol data. When a uniform has no value
        set yet in the compiled program (`KeyError` from `self.program[name]`), seeds it from
        its GLSL type (`vec2`/`vec3`/`vec4` get a zero vector of the right length, anything
        else gets a scalar zero) rather than leaving it unregistered, so a protocol column
        for that uniform can still be applied via `update_stim_state`. `type='all'`
        additionally sweeps everything that is not `varying`/`constant`, independent of a
        uniform's actual declared type.
        """
        self._shared_uniform_states = []
        for i in self.program.variables:
            if i[2] not in ['u_resolution', 'u_time']:
                if type != 'all':
                    if i[0] == type:
                        try:
                            self.create_streaming_state(i[2], list(self.program[i[2]].astype(float)),shared=True)
                        except KeyError:
                            self.warning(f'Uniform {i[2]} has not been set')
                            if i[1] == 'vec2':
                                self.create_streaming_state(i[2], [0, 0])
                            elif i[1] == 'vec3':
                                self.create_streaming_state(i[2], [0, 0, 0])
                            elif i[1] == 'vec4':
                                self.create_streaming_state(i[2], [0, 0, 0, 0])
                            else:
                                self.create_streaming_state(i[2], 0,shared=True)
                        except:
                            self.error(f'Error in creating shared state for uniform: {i[2]}\n{traceback.format_exc()}')
                        self._shared_uniform_states.append(i[2])
                else:
                    if i[0] not in ['varying', 'constant']:
                        self.create_streaming_state(i[2], self.program[i[2]],shared=True)
                        self._shared_uniform_states.append(i[2])

    def remove_shared_uniform_state(self):
        """Unregister every streaming state created by the last `create_shared_uniform_state` call.

        Called from `_init_program` before rebuilding, so a shader swap does not leave the
        previous shader's uniform states (and their shared-memory segments) registered
        alongside the new shader's.
        """
        for i in self._shared_uniform_states:
            self.remove_streaming_state(self.name,i)

    def check_variables(self):
        """Report which GL program variables are unresolved: pending, and unset.

        `redundant_variables` come straight from vispy's own `_pending_variables` -- names
        the shader declares but the program has never assigned a value to. `unsettled_variables`
        are non-varying/non-constant variables vispy has no user-supplied value for at all;
        `_init_program` seeds those from the streaming state so a freshly built program still
        renders something instead of leaving GL attributes uninitialized.
        """
        redundant_variables = list(self.program._pending_variables.keys())
        unsettled_variables = []
        for i in self.program.variables:
            if i[0] not in ['varying', 'constant']:
                if i[2] not in self.program._user_variables.keys():
                    unsettled_variables.append(i[2])
        return redundant_variables, unsettled_variables

    def on_time(self, t):
        """Per-tick hook: sync fullscreen/protocol state from the trigger minion, then render.

        Overrides `StreamingCompiler.on_time`: in addition to the base class's
        streaming-trigger check (via `super().on_time(t)`), this pulls the fullscreen flag
        and runs or ends the protocol depending on `get_run_signal()`, then pushes the
        current time into the `u_time` uniform and requests a repaint. Order matters --
        protocol state is applied before `super().on_time(t)` runs `_streaming()`, so a
        protocol-driven uniform change streams on the same tick it takes effect, and
        `u_time`/`update()` run last so the draw reflects everything decided above.
        """
        self.set_fullscreen()
        running = self.get_run_signal()
        if running:
            self._run_protocol()
        else:
            if self._protocol_start_time is not None:
                self._end_protocol()
        super().on_time(t)
        if self.program is not None:
            self.program['u_time'] = t
            self.update()

    def set_fullscreen(self):
        """Adopt the trigger minion's APP_FULLSCREEN flag when it changes.

        Called every tick from `on_time`; only updates `self.fullscreen` on the tick the
        flag actually flips (via `watch_state`), never on a stale/None read.
        """
        fullscreen = self.get_state_from(self._trigger_minion, _contract.APP_FULLSCREEN)
        if self.watch_state(_contract.APP_FULLSCREEN, fullscreen) and fullscreen is not None:
            self.fullscreen = fullscreen

    def on_draw(self, event):
        """Vispy draw-event hook: render the program to screen and publish the FBO preview.

        Overrides `vispy.app.Canvas.on_draw`, called by vispy's own event loop whenever
        `update()` requests a repaint -- not directly by `on_time`. Does nothing if no
        program is loaded. Publishes `_fbo.read()` (RGB only, alpha dropped) as the
        APP_FBO_PREVIEW shared buffer on every draw, which is how a GUI preview stays in
        sync with what is actually rendered rather than with the protocol's notion of state.
        """
        if self.program is not None:
            gloo.clear()
            gloo.set_viewport(0, 0, *self.physical_size)
            self.program.draw('triangle_strip')
            # thumbnail = resize_with_padding(self._fbo.read()[...,:-1], *self._max_frame_shape[::-1])
            self.set_state(_contract.APP_FBO_PREVIEW, self._fbo.read()[...,:-1])
            # print(f"FPS: {1/(time()-self._frame_delta)}")
            # self._frame_delta = time()

    def get_protocol_fn(self):
        """Load a new protocol table from the trigger minion's PROTOCOL_FILE state, if one was set.

        Called every tick from `get_run_signal`, but only takes effect while no protocol is
        already running (`_protocol_start_time is None`) and only on the tick PROTOCOL_FILE
        actually changes. Validates that every currently-shared uniform has a matching
        column in the sheet before accepting it; on a mismatch the load is rolled back
        (`_protocol`/`_protocolFn` reset to None) rather than left half-applied, since
        `_run_protocol` indexes columns by uniform name and would otherwise KeyError mid-run.
        """
        if self._protocol_start_time is None:  # Only execute if protocol is not running
            protocolFn = self.get_state_from(self._trigger_minion, _contract.PROTOCOL_FILE)
            if self.watch_state(_contract.PROTOCOL_FILE, protocolFn) and protocolFn not in ['', None]:
                self.info(f"Loading protocol from {protocolFn}")
                self._protocol = pd.read_excel(protocolFn)
                self._protocolFn = protocolFn
                missing_uniforms = [k for k in self._shared_uniform_states if k not in self._protocol.columns]
                if len(missing_uniforms) > 0:
                    self.error(
                        f'Protocol cannot be executed because the following uniforms are missing in the protocol file: {missing_uniforms}')
                    self._protocol = None
                    self._protocolFn = None
                else:
                    self._time_index_col = self._protocol[_contract.PROTOCOL_TIME_COLUMN].to_numpy()

    def get_FS(self):
        """Load a new shader from the trigger minion's APP_SHADER_FILE state, if one was set.

        Called every tick from `get_run_signal`, but only while no protocol is running --
        swapping shaders mid-protocol would invalidate the uniform set `get_protocol_fn`
        already validated against the loaded protocol table.
        """
        if self._protocol_start_time is None:  # Only execute if protocol is not running
            self._FSFn = self.get_state_from(self._trigger_minion, _contract.APP_SHADER_FILE)
            if self.watch_state(_contract.APP_SHADER_FILE, self._FSFn) and self._FSFn not in ['', None]:
                self.info(f"Loading shader from {self._FSFn}")
                self._init_program()
                self.info(f"Rendering program updated")

    def get_run_signal(self):
        """Poll for shader/protocol updates and report whether the protocol should be running now.

        Called every tick from `on_time`. Always refreshes the shader and protocol table
        first (`get_FS`/`get_protocol_fn`), then reads PROTOCOL_RUN only if both are loaded
        -- a protocol cannot start without a shader whose uniforms it can drive. On the tick
        PROTOCOL_RUN actually flips, starts (`_start_protocol`) or ends (`_end_protocol`) the
        run as a side effect of answering the question; on any other tick it just reports the
        flag's current value with no side effect.
        """
        self.get_FS()
        self.get_protocol_fn()
        if self._protocol is not None and self.FS is not None:  # Only execute if protocol and FS are loaded
            runSignal = self.get_state_from(self._trigger_minion, _contract.PROTOCOL_RUN)
            if self.watch_state(_contract.PROTOCOL_RUN, runSignal):
                if runSignal:
                    self._start_protocol()
                    return True
                else:  # if self._running_protocol has been switched off, return False to stop protocal running and reset related params
                    self._end_protocol()
                    return False
            else:
                return runSignal
        else:
            return False

    def _start_protocol(self):
        """Begin a protocol run: record its filenames as streaming state and reset the run clock.

        Called once, from `get_run_signal`, on the tick PROTOCOL_RUN turns on. Sets
        `_protocol_start_time` to the current timestamp, which is what other methods check
        to decide whether a protocol is active at all, and resets PROTOCOL_CMD_INDEX to 0 so
        `_run_protocol`'s "has cmd_idx changed" check fires on the very first command too.
        """
        self.info('Starting protocol')
        self.set_streaming_state(_contract.PROTOCOL_FILE, self._protocolFn)
        self.set_streaming_state(_contract.APP_SHADER_FILE, self._FSFn)
        self._protocol_start_time = self.get_timestamp()
        self.set_streaming_state(_contract.PROTOCOL_CMD_INDEX, 0)

    def _run_protocol(self):
        """Advance the protocol clock, apply the current row's commands, and stream on change.

        Called every tick from `on_time` while a protocol is running. `cmd_idx` is derived
        by counting how many of the protocol's timestamped rows have already elapsed, so a
        slow tick can skip rows entirely (rows are not guaranteed to run one per tick) -- but
        a repeated `cmd_idx` (protocol running faster than its own rows) is caught by
        `watch_state` and only applies each row's commands once. Ends the protocol itself
        once `cmd_idx` reaches the last row, from inside this same call, rather than waiting
        for `get_run_signal` to notice on a later tick.
        """
        self._running_time = self.get_timestamp() - self._protocol_start_time
        cmd_idx = sum(self._running_time >= self._time_index_col) - 1
        if self.watch_state(_contract.PROTOCOL_CMD_INDEX, cmd_idx):
            cmd = self._protocol.iloc[cmd_idx, :]
            for k, v in cmd.items():
                self.update_stim_state(k, v)
            self.set_streaming_state(_contract.PROTOCOL_CMD_INDEX, cmd_idx)
            if cmd_idx >= len(self._time_index_col) - 1:
                self._end_protocol()
            self.exec_stim_cmd()

    def exec_stim_cmd(self):
        """Hook run once per applied protocol command; base implementation just requests a repaint.

        Called from `_run_protocol` after `update_stim_state` has applied every column of
        the current row. Exists so a subclass can add stimulus-specific side effects (e.g.
        triggering hardware) on the same cadence as uniform updates, without overriding
        `_run_protocol` itself.
        """
        self.update()

    def update_stim_state(self, k, v):
        """Apply one protocol column's value to the matching shader uniform, and stream it.

        Called once per column, per row, from `_run_protocol`. Silently skips any column
        whose name is not a currently shared uniform -- e.g. non-uniform bookkeeping columns
        in the protocol sheet -- rather than treating it as an error.
        """
        if k in self._shared_uniform_states:
            self.program[k] = v
            self.set_streaming_state(k, v)

    def _end_protocol(self):
        """Stop the running protocol, clear the screen, and hand PROTOCOL_RUN back to the trigger minion.

        Called either from `_run_protocol` (the last row was just applied) or from
        `get_run_signal`/`on_time` (PROTOCOL_RUN was turned off externally, or turned on with
        no protocol loaded). Writing PROTOCOL_RUN back to the trigger minion, not just
        locally, is what lets a GUI-side toggle reflect a protocol that ended on its own by
        running out of rows.
        """
        gloo.clear('black')
        self.update()

        self._protocol_start_time = None
        # self.FS = None
        self.set_streaming_state(_contract.PROTOCOL_CMD_INDEX, -1)
        self.set_state_to(self._trigger_minion, _contract.PROTOCOL_RUN, False)
        self._running_time = 0
        self.info('Protocol ended')

    def on_resize(self, event):
        """Vispy resize-event hook: keep the GL viewport and shader resolution in sync with the window.

        Overrides `vispy.app.Canvas.on_resize`, called by vispy whenever the window changes
        size -- not from `on_time`. Writes directly into `self.program['u_resolution']`
        rather than through `update_stim_state`/streaming, since window resolution is not
        protocol-driven state.
        """
        # Define how should be rendered image should be resized by changing window size
        gloo.set_viewport(0, 0, *self.physical_size)
        self.program['u_resolution'] = self.size
        # self._fbo.resize(self.physical_size[::-1])


    def on_close(self):
        """Vispy/window close hook: mark this minion stopped and close the window.

        Overrides both `AbstractCompiler.on_close` (a no-op) and `vispy.app.Canvas.on_close`.
        `AbstractCompiler._on_close` already sets FRAMEWORK_STATUS to -1 before calling this,
        but it is set again directly here so this method also does the right thing when
        vispy itself invokes it, straight from a window-close event, without going through
        `_on_close` at all.
        """
        self.set_state(_contract.FRAMEWORK_STATUS, -1)
        self.close()
