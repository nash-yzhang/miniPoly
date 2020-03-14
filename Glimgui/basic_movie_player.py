from scipy.ndimage import gaussian_filter
from Glimgui.glarage import *
from glumpy import gl, glm, gloo
import imgui
import cv2

self = None


def prepare():
    # self._clock.set_fps_limit(60)
    self.cam = cv2.VideoCapture(0)
    self.cam.set(cv2.CAP_PROP_FPS, 20)
    shader_folder = './shaderfile/'
    vertex_shader_fn = 'VS_basic_tex.glsl'
    frag_shader_fn = 'FS_basic_tex.glsl'


    # Our operations on the frame come here

    vertex = load_shaderfile(shader_folder + vertex_shader_fn)
    fragment = load_shaderfile(shader_folder + frag_shader_fn)

    self.mov_player = gloo.Program(vertex, fragment)
    self.mov_player['a_pos'] = [(-1,-1), (-1,+1), (+1,-1), (+1,+1)]
    self.mov_player['a_texcoord'] = [(1.,1.), (1.,0.), (0.,1.), (0.,0.)]
    _, self._buffer_frame = self.cam.read()
    self._buffer_frame = self._buffer_frame[:,:,::-1]
    self.mov_player['texture'] = self._buffer_frame

    self.mov_player2 = gloo.Program(vertex, fragment)
    self.mov_player2['a_pos'] = [(-1,-1), (-1,+1), (+1,-1), (+1,+1)]
    self.mov_player2['a_texcoord'] = [(1.,1.), (1.,0.), (0.,1.), (0.,0.)]
    self.mov_player2['texture'] = self._buffer_frame

    self._draw_second = False

def on_draw(dt):
    # _, frame = self.cam.read()
    # gl.glEnable(gl.GL_DEPTH_TEST)
    self.clear()
    if self._draw_second:
        self.mov_player['texture'] = self._buffer_frame
        self.mov_player.draw(gl.GL_TRIANGLE_STRIP)
    else:
        self.mov_player2['texture'] = self._buffer_frame
        self.mov_player2.draw(gl.GL_TRIANGLE_STRIP)
    self._draw_second = not self._draw_second


def set_imgui_widgets():
    imgui.begin('FPS')
    imgui.text("Frame duration: %.2f ms" % (self.dt * 1000))
    imgui.text("FPS: %d Hz" % round(1 / (self.dt + 1e-8)))
    imgui.end()
    _,self._buffer_frame = self.cam.read()
    self._buffer_frame = self._buffer_frame[:, :, ::-1]
    # if not self._has_pop:
    imgui.begin("Cam 1", True)
    ww, wh = imgui.get_window_size()
    winPos = imgui.get_cursor_screen_pos()
    self.clear()
    self._framebuffer.activate()
    self.dispatch_event("on_draw", .0)
    self._framebuffer.deactivate()
    draw_list = imgui.get_window_draw_list()
    draw_list.add_image(self._framebuffer.color[0]._handle, tuple(winPos), tuple([winPos[0] + ww, winPos[1] + wh]),
                        (0, 1), (1, 0))
    imgui.end()

    imgui.begin("Cam 2", True)
    ww, wh = imgui.get_window_size()
    winPos = imgui.get_cursor_screen_pos()
    self.clear()
    self._framebuffer.activate()
    self.dispatch_event("on_draw", .0)
    self._framebuffer.deactivate()
    draw_list = imgui.get_window_draw_list()
    draw_list.add_image(self._framebuffer.color[0]._handle, tuple(winPos), tuple([winPos[0] + ww, winPos[1] + wh]),
                        (0, 1), (1, 0))
    imgui.end()


def pop_on_resize(width, height):
    pass
    # self.Shape['u_scale'] = height / width, 1