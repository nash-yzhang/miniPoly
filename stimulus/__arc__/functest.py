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

    # _isalive = True
    # self.minion_plug.put(locals(),['_isalive'])
    # self.minion_plug.give('report', ['_isalive'])

def set_widgets():
    if imgui.begin_main_menu_bar():
        if imgui.begin_menu("Command", True):
            clicked_restart, _ = imgui.menu_item(
                "Restart GLwindow", '', False, True
            )
            if clicked_restart:
                self.window_state[1] = True
            imgui.end_menu()
        imgui.end_main_menu_bar()

    # self.minion_plug.put(self,['dt'])
    # self.minion_plug.give('report',['dt'])

    imgui.begin("Custom window", True)
    _, self.elv = imgui.slider_float("Azi", self.elv, 0, 360)
    _, self.azi = imgui.slider_float("Elv", self.azi, 0, 360)
    _, self.dist = imgui.slider_float("Dist", self.dist, -2, -10)
    _, self.bgcolor = imgui.color_edit4('test', *self.bgcolor, True)
    imgui.text("FPS: %d"%(1/(self.dt+1e-5)))
    imgui.end()
    self.quad['u_model'] = glm.rotate(np.eye(4), self.azi, 0, 0, 1) @ glm.rotate(np.eye(4), self.elv, 0, 1, 0)
    self.quad['u_view'] = glm.translation(0, 0, self.dist)
    
    if self._init_glwin == True:
        imgui.set_next_window_position(100,100)
        self._init_glwin = False
    _, self.window_state[1] = imgui.begin("GLView", True)#, flags = imgui.WINDOW_NO_TITLE_BAR)
    ww, wh = imgui.get_window_size()
    winPos = imgui.get_cursor_screen_pos()
    self.quad['u_projection'] = glm.perspective(45.0, ww / float(wh), 2.0, 100.0)
    self.clear()
    self._framebuffer.activate()
    self.dispatch_event("on_draw", self.dt)
    self._framebuffer.deactivate()
    draw_list = imgui.get_window_draw_list()
    draw_list.add_image(self._framebuffer.color[0]._handle, tuple(winPos), tuple([winPos[0] + ww, winPos[1] + wh]),
                        (0, 0), (1, 1))
    imgui.invisible_button("popup", ww-30, wh-50)
    if imgui.begin_popup_context_item("Item Context Menu", mouse_button=0):
        if imgui.selectable("Pop out")[1]:
            self.pop(ww,wh,winPos[0],winPos[1],title = 'GLView')
        imgui.end_popup()
    imgui.end()


def on_init():
    gl.glEnable(gl.GL_DEPTH_TEST)

def pop_on_resize(width,height):
    self.quad['u_projection'] = glm.perspective(45.0, max(width,1.) / max(height,1.), 2.0, 100.0)

def on_draw(dt):
    # TODO: Finalize HERE to make window pop-able
    # self._framebuffer.activate()
    self.clear(self.bgcolor)
    gl.glEnable(gl.GL_DEPTH_TEST)
    self.quad.draw(gl.GL_TRIANGLES, self.I)
    # self._framebuffer.deactivate()

# def terminate():
#     _isalive = False
#     self.minion_plug.put(locals(),['_isalive'])
#     self.minion_plug.give('report', ['_isalive'])
