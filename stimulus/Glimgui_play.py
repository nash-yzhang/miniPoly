import imgui
from glumpy import gloo, glm,gl
from Glimgui.GlImgui import glimWindow
import numpy as np

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


glimgui_win = glimWindow(1024,720)

@glimgui_win.event
def prepare():
    glimgui_win.quad = gloo.Program(vertex, fragment)
    V = np.zeros(8, [("a_position", np.float32, 3),
                     ("a_color", np.float32, 4)])
    V["a_position"] = [[1, 1, 1], [-1, 1, 1], [-1, -1, 1], [1, -1, 1],
                       [1, -1, -1], [1, 1, -1], [-1, 1, -1], [-1, -1, -1]]
    V["a_color"] = [[0, 1, 1, 1], [0, 0, 1, 1], [0, 0, 0, 1], [0, 1, 0, 1],
                    [1, 1, 0, 1], [1, 1, 1, 1], [1, 0, 1, 1], [1, 0, 0, 1]]
    V = V.view(gloo.VertexBuffer)
    I = np.array([0, 1, 2, 0, 2, 3, 0, 3, 4, 0, 4, 5, 0, 5, 6, 0, 6, 1,
                  1, 6, 7, 1, 7, 2, 7, 4, 3, 7, 3, 2, 4, 7, 6, 4, 6, 5], dtype=np.uint32)
    glimgui_win.I = I.view(gloo.IndexBuffer)
    model = np.eye(4, dtype=np.float32)
    glimgui_win.quad['u_projection'] = glm.perspective(45.0, glimgui_win._init_height / glimgui_win._init_width, 2.0, 100.0)
    glimgui_win.quad['u_model'] = model
    glimgui_win.quad['u_view'] = glm.translation(0, 0, -5)
    glimgui_win.quad['u_pos_corr'] = np.array([0, 0])
    glimgui_win.quad['u_scale_corr'] = np.array([1, 1])
    glimgui_win.bgcolor = 0, 0.5, 1, 1
    glimgui_win.azi = 0
    glimgui_win.elv = 0
    glimgui_win.dist = -5
    glimgui_win.quad.bind(V)
    texture = np.zeros((glimgui_win._init_height, glimgui_win._init_width, 4), np.float32).view(gloo.TextureFloat2D)
    depthbuffer = gloo.DepthBuffer(glimgui_win._init_width, glimgui_win._init_height)

    io = imgui.get_io()
    glimgui_win.font = io.fonts.add_font_from_file_ttf("C:\\Windows\Fonts\seguisb.ttf", 20)
    glimgui_win.imgui_renderer.refresh_font_texture()

    glimgui_win.framebuffer = gloo.FrameBuffer(color=[texture], depth=depthbuffer)
    glimgui_win.window_state = [True, True]

@glimgui_win.event
def set_imgui_widgets():
    if imgui.begin_main_menu_bar():
        if imgui.begin_menu("Command", True):
            clicked_restart, _ = imgui.menu_item(
                "Restart GLwindow", '', False, True
            )
            if clicked_restart:
                glimgui_win.window_state[1] = True
            imgui.end_menu()
        imgui.end_main_menu_bar()

    imgui.set_next_window_position(10, 40)
    imgui.set_next_window_size(250, 150)

    imgui.begin("Controller", True)
    _, glimgui_win.elv = imgui.slider_float("Azi", glimgui_win.elv, 0, 360)
    _, glimgui_win.azi = imgui.slider_float("Elv", glimgui_win.azi, 0, 360)
    _, glimgui_win.dist = imgui.slider_float("Dist", glimgui_win.dist, -2, -10)
    _, glimgui_win.bgcolor = imgui.color_edit4('test', *glimgui_win.bgcolor, True)
    imgui.text("FPS:%.1f Hz" % (1 / max(glimgui_win.dt, 1e-10)))
    imgui.end()





    if glimgui_win.window_state[1]:
        _, glimgui_win.window_state[1] = imgui.begin("New window", True)
        ww, wh = imgui.get_window_size()
        winPos = imgui.get_cursor_screen_pos()
        glimgui_win.quad['u_projection'] = glm.perspective(45.0, ww / float(wh), 2.0, 100.0)
        glimgui_win.dispatch_event("on_draw", glimgui_win.dt)

        draw_list = imgui.get_window_draw_list()
        draw_list.add_image(glimgui_win.framebuffer.color[0]._handle, tuple(winPos), tuple([winPos[0] + ww, winPos[1] + wh]),
                            (0, 1), (1, 0))
        imgui.end()

@glimgui_win.event
def on_resize(width, height):
    pass

@glimgui_win.event
def on_init():
    gl.glEnable(gl.GL_DEPTH_TEST)

@glimgui_win.event
def on_draw(dt):
    glimgui_win.quad['u_model'] = glm.rotate(np.eye(4), glimgui_win.azi, 0, 0, 1) @ glm.rotate(np.eye(4), glimgui_win.elv, 0, 1, 0)
    glimgui_win.quad['u_view'] = glm.translation(0,0,glimgui_win.dist)
    glimgui_win.quad['u_pos_corr'] = np.array([(glimgui_win._init_width-glimgui_win.width)/glimgui_win.width,(glimgui_win._init_height-glimgui_win.height)/glimgui_win.height])
    glimgui_win.quad['u_scale_corr'] = 1/np.array([glimgui_win.width/glimgui_win._init_width,glimgui_win.height/glimgui_win._init_height])#/np.array([1,(wh*mw._init_width)/(ww*mw._init_height)])
    glimgui_win.clear()
    gl.glEnable(gl.GL_DEPTH_TEST)
    glimgui_win.framebuffer.activate()
    glimgui_win.clear(glimgui_win.bgcolor)
    glimgui_win.quad.draw(gl.GL_TRIANGLES,glimgui_win.I)
    glimgui_win.framebuffer.deactivate()


glimgui_win.start()