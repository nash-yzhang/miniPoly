import imgui
from glumpy import gloo, glm,gl
import numpy as np

self = None

def prepare():
    self._clock.set_fps_limit(50)
    vertex = """
    uniform mat4   u_model;         // Model matrix
    uniform mat4   u_view;          // View matrix
    uniform vec2   u_scale_corr;       // 2D position correction
    uniform vec2   u_pos_corr;       // 2D position correction
    uniform mat4   u_projection;    // Projection matrix
    attribute vec4 a_color;         // Vertex color
    attribute vec3 a_position;      // Vertex position
    varying vec4   v_color;         // Interpolated fragment color (out)
    void main()
    {
        v_color = a_color;
        gl_Position = u_projection * u_view * u_model * vec4(a_position,1.0);
        gl_Position.xy *= u_scale_corr;
        gl_Position.xy += u_pos_corr*gl_Position.w;
    } """

    fragment = """
    varying vec4   v_color;         // Interpolated fragment color (in)
    void main()
    {
        gl_FragColor = v_color;
    } """
    self.quad = gloo.Program(vertex, fragment)
    V = np.zeros(8, [("a_position", np.float32, 3),
                     ("a_color", np.float32, 4)])
    V["a_position"] = [[1, 1, 1], [-1, 1, 1], [-1, -1, 1], [1, -1, 1],
                       [1, -1, -1], [1, 1, -1], [-1, 1, -1], [-1, -1, -1]]
    V["a_color"] = [[0, 1, 1, 1], [0, 0, 1, 1], [0, 0, 0, 1], [0, 1, 0, 1],
                    [1, 1, 0, 1], [1, 1, 1, 1], [1, 0, 1, 1], [1, 0, 0, 1]]
    V = V.view(gloo.VertexBuffer)
    I = np.array([0, 1, 2, 0, 2, 3, 0, 3, 4, 0, 4, 5, 0, 5, 6, 0, 6, 1,
                  1, 6, 7, 1, 7, 2, 7, 4, 3, 7, 3, 2, 4, 7, 6, 4, 6, 5], dtype=np.uint32)
    self.I = I.view(gloo.IndexBuffer)
    model = np.eye(4, dtype=np.float32)
    self.quad['u_projection'] = glm.perspective(45.0, self._init_height / self._init_width, 2.0, 100.0)
    self.quad['u_model'] = model
    self.quad['u_view'] = glm.translation(0, 0, -5)
    self.quad['u_pos_corr'] = np.array([0, 0])
    self.quad['u_scale_corr'] = np.array([1, 1])
    self.bgcolor = 0, 0.5, 1, 1
    self.azi = 0
    self.elv = 0
    self.dist = -5
    self.quad.bind(V)
    self.window_state = [True, True]
    self._init_glwin = True
    self._glwinpos = [0,0]
    self.t = 0
    # self.dispatch_event("on_resize")

def draw_main():
    self.minion_plug.get('controller',['elv','azi','dist','bgcolor','t'])
    if 'elv' in self.minion_plug.inbox.keys():
        self.elv = self.minion_plug.inbox['elv']
    if 'azi' in self.minion_plug.inbox.keys():
        self.azi = self.minion_plug.inbox['azi']
    if 'dist' in self.minion_plug.inbox.keys():
        self.dist = self.minion_plug.inbox['dist']
    if 'bgcolor' in self.minion_plug.inbox.keys():
        self.bgcolor = self.minion_plug.inbox['bgcolor']

    self.quad['u_model'] = glm.rotate(np.eye(4), self.azi, 0, 0, 1) @ glm.rotate(np.eye(4), self.elv, 0, 1, 0)
    self.quad['u_view'] = glm.translation(0, 0, self.dist)
    self.dispatch_event("on_draw", self.dt)
    if 't' in self.minion_plug.inbox.keys():
        self.t = self.minion_plug.inbox['t']+1
    self.minion_plug.put(self, ['t'])
    self.minion_plug.give('controller',['t'])


def on_draw(dt):
    self.clear(self.bgcolor)
    gl.glEnable(gl.GL_DEPTH_TEST)
    self.quad.draw(gl.GL_TRIANGLES, self.I)

def on_resize(width,height):
    self.quad['u_projection'] = glm.perspective(45.0, max(width,1.) / max(height,1.), 2.0, 100.0)

def on_init():
    gl.glEnable(gl.GL_DEPTH_TEST)