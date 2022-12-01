import os

from sphModel import *
import numpy as np
from vispy import app,gloo
from vispy.util.transforms import translate, rotate, perspective

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

_default_sphere_VS = """
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

_default_sphere_FS = """
    uniform float u_time;
    void main() {
        gl_FragColor = vec4(vec3(sin(u_time),cos(u_time),sin(u_time+1.57/2))/2.+.5, 1.);
    }
    """
class GLCanvas(app.Canvas):
    def __init__(self,*args,**kwargs):
        app.Canvas.__init__(self, *args, **kwargs)
        self.timer = app.Timer('auto', self.on_timer, start=True)

    def load(self,renderer):
        self.VS = renderer.VS
        self.FS = renderer.FS
        self.program = renderer.program
        self.on_draw = renderer.on_draw
        self.on_resize = renderer.on_resize
        self.init_renderer = renderer.init_renderer
        self.init_renderer()

    def on_timer(self, event):
        self.update()


class Renderer:

    def __init__(self,canvas):
        self.canvas = canvas

    def init_renderer(self):
        pass

    def reload(self,FS):
        self.FS = FS
        self.program = gloo.Program(self.VS,self.FS)
        self.init_renderer()

    def on_resize(self, event):
        gloo.set_viewport(0, 0, *self.canvas.physical_size)
        self.program['u_resolution'] = (self.canvas.size[0],self.canvas.size[1])

class planeRenderer(Renderer):

    def __init__(self,canvas):
        super().__init__(canvas)
        self.VS = _default_plane_VS
        self.FS = _default_plane_FS
        self.program = gloo.Program(self.VS,self.FS)

    def init_renderer(self):
        self.program['a_pos'] = np.array([[-1.,-1.],[-1.,1.],[1.,-1.],[1.,1.]],np.float32)
        self.program['u_time'] = 0
        gloo.set_state(clear_color='w')
        self.program['u_resolution'] = (self.canvas.size[0],self.canvas.size[1])

    def on_draw(self,event):
        gloo.clear()
        u_time = self.canvas.timer.elapsed
        self.program['u_time'] = u_time
        self.program.draw('triangle_strip')


class sphereRenderer(Renderer):

    def __init__(self,canvas):
        super().__init__(canvas)
        self.VS = _default_sphere_VS
        self.FS = _default_sphere_FS
        self.program = gloo.Program(self.VS,self.FS)

    def init_renderer(self):
        self._vertices,self._faces = uv_sphere(60,40)
        self.translate = -5
        self.view = translate((0, 0, self.translate))
        self.model = np.eye(4, dtype=np.float32)
        self.program['u_model'] = self.model
        self.program['u_view'] = self.view
        self.phi, self.theta = 0, 0
        self.program['a_pos'] = qn.qn(self._vertices)['xyz'].astype(np.float32)
        projection = perspective(45.0, self.canvas.size[0] / float(self.canvas.size[1]),
                                 2.0, 10.0)
        self.program['u_projection'] = projection
        self.sph_index = gloo.IndexBuffer(self._faces.astype(np.uint16))
        gloo.set_state(clear_color='k', depth_test=True,)
        self.canvas.on_mouse_motion = self.on_mouse_motion
        self.canvas.on_mouse_wheel = self.on_mouse_wheel
        self.canvas.events.mouse_press.connect((self.canvas, "on_mouse_motion"))
        self.canvas.events.mouse_release.connect((self.canvas, "on_mouse_motion"))
        self.canvas.events.mouse_move.connect((self.canvas, "on_mouse_motion"))

    def on_draw(self,event):
        gloo.clear(depth=True)
        u_time = self.canvas.timer.elapsed
        self.program['u_time'] = u_time
        self.program.draw('triangles',self.sph_index)

    # def reload(self,FS):
    #     self.FS = FS
    #     self.program = gloo.Program(self.VS,self.FS)
    #     self.view = translate((0, 0, self.translate))
    #     self.model = np.eye(4, dtype=np.float32)
    #     self.program['u_model'] = self.model
    #     self.program['u_view'] = self.view
    #     self.phi, self.theta = 0, 0
    #     self.program['a_pos'] = qn.qn(self._vertices)['xyz'].astype(np.float32)
    #     projection = perspective(45.0, self.canvas.size[0] / float(self.canvas.size[1]),
    #                              2.0, 10.0)
    #     self.program['u_projection'] = projection

    def on_resize(self, event):
        gloo.set_viewport(0, 0, *self.canvas.physical_size)
        projection = perspective(45.0, self.canvas.size[0] / float(self.canvas.size[1]),
                                 2.0, 10.0)
        self.program['u_projection'] = projection

    def on_mouse_motion(self, event):
        if event.is_dragging and len(event.trail()) > 1:
            delta = event.trail()
            delta = delta[-2, :] - delta[-1, :]
            self.phi += delta[0] / self.canvas.size[0] * np.pi * 100
            self.theta -= delta[1] / self.canvas.size[1] * np.pi * 50
            self.model = np.dot(rotate(self.phi, (0, -1, 0)),
                                rotate(self.theta, (1, 0, 0)))
            self.program['u_model'] = self.model

    def on_mouse_wheel(self, event):
        self.translate += event.delta[1] / 10
        self.view = translate((0, 0, self.translate))
        self.program['u_view'] = self.view
        self.canvas.update()
