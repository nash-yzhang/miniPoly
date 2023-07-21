import numpy as np
from importlib import util
import sys

from vispy import gloo, app

from miniPoly.process.minion import AbstractMinionMixin

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


class GLDisplay(app.Canvas, AbstractMinionMixin):
    def __init__(self, handler, *args, controllerProcName=None, **kwargs):
        super().__init__(*args, **kwargs)
        app.Canvas.__init__(self, *args, **kwargs)
        self.timer = app.Timer('auto', self.on_timer, start=True)

        self._processHandler = handler
        self._setTime = 0
        self._tic = 0
        if controllerProcName:
            self.controllerProcName = controllerProcName

    @property
    def controllerProcName(self):
        return self._controllerProcName

    @controllerProcName.setter
    def controllerProcName(self, value):
        self._controllerProcName = value

    def load(self,renderer):
        self.VS = renderer.VS
        self.FS = renderer.FS
        self.program = renderer.program
        self.on_draw = renderer.on_draw
        self.on_resize = renderer.on_resize
        self.init_renderer = renderer.init_renderer
        self.init_renderer()

    def parse_msg(self, msg_type, msg):
        if msg_type == 'rendering_script':
            self.rendererScriptName = msg
            self.rendererName = self.rendererScriptName.split("/")[-1][:-3]
            self._processHandler.info(
                "Received rendering script [{}] from [{}]".format(self.rendererScriptName, self.controllerProcName))
            self.importModuleFromPath()
            self._renderer = self.imported.Renderer(self)
            self.load(self._renderer)
            self._processHandler.info("Running script [{}]".format(self.rendererScriptName))
        elif msg_type == 'rendering_shader':
            self._renderer.reload(msg)

    def on_timer(self, event):

        if self.timer.elapsed - self._setTime > .01:  # Limit the call frequency to 1 second

            # Check if any remote calls have been set first before further processing
            if self._processHandler.status <= 0:
                self.on_close()
                return None

            self._setTime = np.floor(self.timer.elapsed)
            self.get(self.controllerProcName)
        self.update()

    def on_close(self):
        self.close()

    def importModuleFromPath(self):
        spec = util.spec_from_file_location(self.rendererName, location=self.rendererScriptName)
        self.imported = util.module_from_spec(spec)
        sys.modules[self.rendererName] = self.imported
        spec.loader.exec_module(self.imported)


class GLRenderer:

    def __init__(self, canvas):

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
        self.program['a_pos'] = np.array([[-1., -1.], [-1., 1.], [1., -1.], [1., 1.]], np.float32)  # /2.
        self.program['u_time'] = 0
        self.program['u_alpha'] = np.float32(1)
        gloo.set_state("translucent")
        self.program['u_resolution'] = (self.canvas.size[0], self.canvas.size[1])

    def reload(self,FS):
        self.FS = FS
        self.program = gloo.Program(self.VS,self.FS)
        self.init_renderer()

    def on_draw(self, event):
        gloo.clear('white')
        u_time = self.canvas.timer.elapsed
        self.program['u_time'] = u_time
        self.program.draw('triangle_strip')

    def on_resize(self, event):
        gloo.set_viewport(0, 0, *self.canvas.physical_size)
        self.program['u_resolution'] = (self.canvas.size[0],self.canvas.size[1])
