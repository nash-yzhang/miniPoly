import glfw
import imgui
from imgui.integrations.glfw import GlfwRenderer
from glumpy import app, gloo, glm,gl

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
import numpy as np
def quad_init():
    quad = gloo.Program(vertex, fragment)
    V = np.zeros(8, [("a_position", np.float32, 3),
                     ("a_color", np.float32, 4)])
    V["a_position"] = [[1, 1, 1], [-1, 1, 1], [-1, -1, 1], [1, -1, 1],
                       [1, -1, -1], [1, 1, -1], [-1, 1, -1], [-1, -1, -1]]
    V["a_color"] = [[0, 1, 1, 1], [0, 0, 1, 1], [0, 0, 0, 1], [0, 1, 0, 1],
                    [1, 1, 0, 1], [1, 1, 1, 1], [1, 0, 1, 1], [1, 0, 0, 1]]
    V = V.view(gloo.VertexBuffer)
    quad.bind(V)
    return quad


def main():
    window,mw = impl_glfw_init()
    imgui.create_context()
    impl = GlfwRenderer(window)
    quad = quad_init()
    texture = np.zeros((mw.init_height, mw.init_width, 4), np.float32).view(gloo.TextureFloat2D)
    depthbuffer = gloo.DepthBuffer(mw.init_width,mw.init_height)
    framebuffer = gloo.FrameBuffer(color=[texture],depth=depthbuffer)
    @mw.event
    def on_resize(width, height):
        pass

    @mw.event
    def on_init():
        gl.glEnable(gl.GL_DEPTH_TEST)

    @mw.event
    def on_draw(dt):
        quad['u_model'] = glm.rotate(np.eye(4), azi, 0, 0, 1) @ glm.rotate(np.eye(4), elv, 0, 1, 0)
        quad['u_view'] = glm.translation(0,0,dist)
        quad['u_pos_corr'] = np.array([(mw.init_width-mw.width)/mw.width,(mw.init_height-mw.height)/mw.height])
        quad['u_scale_corr'] = 1/np.array([mw.width/mw.init_width,mw.height/mw.init_height])#/np.array([1,(wh*mw.init_width)/(ww*mw.init_height)])
        mw.clear()
        gl.glEnable(gl.GL_DEPTH_TEST)
        framebuffer.activate()
        mw.clear(bgcolor)
        quad.draw(gl.GL_TRIANGLES,I)
        framebuffer.deactivate()

    I = np.array([0, 1, 2, 0, 2, 3, 0, 3, 4, 0, 4, 5, 0, 5, 6, 0, 6, 1,
                  1, 6, 7, 1, 7, 2, 7, 4, 3, 7, 3, 2, 4, 7, 6, 4, 6, 5], dtype=np.uint32)
    I = I.view(gloo.IndexBuffer)
    model = np.eye(4, dtype=np.float32)
    quad['u_projection'] = glm.perspective(45.0, mw.init_height/mw.init_width, 2.0, 100.0)
    quad['u_model'] = model
    quad['u_view'] = glm.translation(0, 0, -5)
    quad['u_pos_corr'] = np.array([0, 0])
    quad['u_scale_corr'] = np.array([1,1])

    bgcolor = 0,0.5,1,1
    azi = 0
    elv = 0
    dist = -5
    while not glfw.window_should_close(window):
        glfw.poll_events()
        impl.process_inputs()

        imgui.new_frame()

        if imgui.begin_main_menu_bar():
            if imgui.begin_menu("File", True):

                clicked_quit, selected_quit = imgui.menu_item(
                    "Quit", 'Cmd+Q', False, True
                )

                if clicked_quit:
                    break

                imgui.end_menu()
            imgui.end_main_menu_bar()

        imgui.begin("Custom window", True)
        _,elv = imgui.slider_float("Azi",elv,0,360)
        _,azi = imgui.slider_float("Elv",azi,0,360)
        _,dist = imgui.slider_float("Dist",dist, -2, -10)
        _,bgcolor = imgui.color_edit4('test',*bgcolor,True)
        imgui.end()

        imgui.begin("New window", True)
        ww,wh = imgui.get_window_size()
        winPos = imgui.get_cursor_screen_pos()
        quad['u_projection'] = glm.perspective(45.0, ww / float(wh), 2.0, 100.0)

        mw.dispatch_event("on_draw",.01)

        draw_list = imgui.get_window_draw_list()
        draw_list.add_image(framebuffer.color[0]._handle,tuple(winPos),tuple([winPos[0]+ww,winPos[1]+wh]),(0,1),(1,0))
        imgui.end()

        imgui.render()
        impl.render(imgui.get_draw_data())
        glfw.swap_buffers(window)

    impl.shutdown()
    glfw.terminate()


def impl_glfw_init():
    width, height = 1024,720
    app.use('glfw')
    metawindow = app.Window(width,height,color = (0.2,0.2,0.3,1))
    window = metawindow._native_window
    fakewindow = glfw.create_window(10, 10, "None", None, None)
    window.__class__ = fakewindow.__class__
    glfw.destroy_window(fakewindow)
    metawindow.init_width = width
    metawindow.init_height=  height


    return window,metawindow

#%%
if __name__ == "__main__":
    main()
