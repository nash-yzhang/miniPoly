from Glimgui.glarage import *
from glumpy import gl, gloo
import imgui
import cv2
import Glimgui.tisgrabber.tisgrabber as IC
import numpy as np
from pyfirmata import Arduino, util


self = None

def prepare():
    shader_folder = './shaderfile/'
    vertex_shader_fn = 'VS_basic_tex.glsl'
    frag_shader_fn = 'FS_basic_tex.glsl'

    self.arduino_board = Arduino('COM3')
    self.arduino_iterator = util.Iterator(self.arduino_board)
    self.arduino_iterator.start()

    self.LED_pin  = self.arduino_board.get_pin('d:11:p')
    self.LED_power = .1
    # self.arduino_board.analog[0].enable_reporting()
    # self.ardiuno_sig = [0.]

    self.camera1 = IC.TIS_CAM()
    self.camera1.DevName = self.camera1.GetDevices()[0].decode("utf-8")
    self.camera1.open(self.camera1.DevName)
    self.camera1.SetVideoFormat("Y16 (640x480)")
    self.camera1.SetFrameRate(30.0)
    self.camera1.SetContinuousMode(0)
    self.camera1.StartLive(0)


    self.camera2 = IC.TIS_CAM()
    self.camera2.DevName = self.camera2.GetDevices()[1].decode("utf-8")
    self.camera2.open(self.camera2.DevName)
    self.camera2.SetVideoFormat("Y16 (640x480)")
    self.camera2.SetFrameRate(30.0)
    self.camera2.SetContinuousMode(0)
    self.camera2.StartLive(0)

    print(self.camera1.DevName)
    print(self.camera2.DevName)

    self._clock.set_fps_limit(30)
    # Our operations on the frame come here

    vertex = load_shaderfile(shader_folder + vertex_shader_fn)
    fragment = load_shaderfile(shader_folder + frag_shader_fn)

    self.mov_player = gloo.Program(vertex, fragment)
    self.mov_player['a_pos'] = [(-1,-1), (-1,+1), (+1,-1), (+1,+1)]
    self.mov_player['a_texcoord'] = [(0.,0.), (0.,1.), (1.,0.), (1.,1.)]
    self.camera1.SnapImage()
    self.cam_buffer1 = self.camera1.GetImage()/255.
    self.mov_player['texture'] = self.cam_buffer1

    self.mov_player2 = gloo.Program(vertex, fragment)
    self.mov_player2['a_pos'] = [(-1,-1), (-1,+1), (+1,-1), (+1,+1)]
    self.mov_player2['a_texcoord'] = [(0.,0.), (0.,1.), (1.,0.), (1.,1.)]
    self.camera2.SnapImage()
    self.cam_buffer2 = self.camera2.GetImage()/255.
    self.mov_player2['texture'] = self.cam_buffer2
    self.dtlist = [(0.,0.)]

    self.vid_fn = './/Output1111.avi'
    self.vidwriter = cv2.VideoWriter(self.vid_fn, cv2.VideoWriter_fourcc(*'XVID'), 30.,
                                     (self.cam_buffer1.shape[1]*2,self.cam_buffer1.shape[0]))
    self.rec_timepoint = []
    self.rec_on = False
    self.rec_button_text = 'Start'
    self._draw_second = False

    self._framebuffer2 = gloo.FrameBuffer(color=np.zeros((self.height, self.width, 4), np.float32).view(gloo.Texture2D))


def on_draw(dt):
    # gl.glEnable(gl.GL_DEPTH_TEST)
    self.clear()
    if self._draw_second:
        self.mov_player['texture'] = self.cam_buffer1
        self.mov_player.draw(gl.GL_TRIANGLE_STRIP)
    else:
        self.mov_player2['texture'] = self.cam_buffer2
        self.mov_player2.draw(gl.GL_TRIANGLE_STRIP)
    self._draw_second = not self._draw_second

def set_widgets():
    fps_min = 15.
    fps_max = 45.
    x_offset = 50.
    # self.ardiuno_sig.append(self.arduino_board.analog[0].read())
    # print(self.ardiuno_sig[-1])
    self.dtlist.append((len(self.dtlist),1/max([self.dt,0.0001])))

    imgui.begin("Video Recording")
    _, vid_fn = imgui.input_text('',self.vid_fn,1024)
    if vid_fn != self.vid_fn:
        self.vid_fn = vid_fn
        self.vidwriter.release()
    imgui.same_line()

    if imgui.button(self.rec_button_text):
        if self.rec_on:
            self.rec_button_text = 'Start'
            self.rec_timepoint[1] = len(self.dtlist)
            self.rec_on = False
            self.vidwriter.release()
        else:
            self.rec_on = True
            if self.rec_button_text == 'Start':
                self.rec_timepoint = [len(self.dtlist),99999]
                vidbuffer_shape = np.hstack([self.cam_buffer1,self.cam_buffer2]).shape
                self.vidwriter = cv2.VideoWriter(self.vid_fn, cv2.VideoWriter_fourcc(*'XVID'), 30.,
                                                 (int(vidbuffer_shape[1]),int(vidbuffer_shape[0])))
                self.rec_button_text = 'Stop'
    _,self.LED_power = imgui.slider_float('LED power', self.LED_power, 0.0, 1.0, '%.2f', 1.0)
    self.LED_pin.write(self.LED_power)
    imgui.begin_child("fps plot", 0.,0.)
    ww,wh = imgui.get_window_size()
    wh *=.7
    winPos = imgui.get_cursor_screen_pos()
    winPos = (winPos[0],winPos[1]+30)
    line_st = int(max([len(self.dtlist)-ww+x_offset,0]))

    dtlist_adapted = np.array(self.dtlist)[line_st:]
    # dtlist_adapted[:, 0] -= line_st*2
    dtlist_adapted[:,1] = (1-(dtlist_adapted[:,1]-fps_min)/(fps_max-fps_min))*wh
    dtlist_adapted += winPos+np.array([-min(dtlist_adapted[:,0])+x_offset,0.])

    # arduino_sig_adapted = np.array(self.ardiuno_sig)[line_st:] * wh + winPos[1]

    draw_list = imgui.get_window_draw_list()
    y_min = winPos[1]
    y_max = winPos[1]+wh
    x_min = min(dtlist_adapted[:,0])
    x_max = max(dtlist_adapted[:,0])
    if self.rec_timepoint:
        rect_st = x_min+max([self.rec_timepoint[0]-line_st,0])
        rect_ed = min([x_max,x_min+self.rec_timepoint[1]-line_st])
        if rect_st<rect_ed:
            draw_list.add_rect_filled(rect_st, y_max, rect_ed, y_min, imgui.get_color_u32_rgba(1,1,0,.5))
    draw_list.add_polyline(dtlist_adapted.tolist(), imgui.get_color_u32_rgba(0., .5, 1, 1), closed=False,
                           thickness=3)
    # from IPython import embed
    # embed()
    # draw_list.add_polyline(np.vstack([dtlist_adapted[:,0],arduino_sig_adapted]).T.tolist(), imgui.get_color_u32_rgba(.5, .5, 1, 1), closed=False, thickness=3)
    draw_list.add_polyline([(winPos[0]+x_offset, winPos[1]), (winPos[0]+x_offset, winPos[1]+wh)], imgui.get_color_u32_rgba(1., 1., 1., .5), closed=False,
                           thickness=4)
    draw_list.add_polyline([(winPos[0]+x_offset, winPos[1]+wh/2.), (winPos[0]+ww, winPos[1]+wh/2)], imgui.get_color_u32_rgba(1., 1., 1., .5), closed=False,
                           thickness=4)
    draw_list.add_text(winPos[0],winPos[1]+wh/2-5,imgui.get_color_u32_rgba(1,1,0,1),'30 Hz')
    draw_list.add_text(winPos[0], winPos[1] + wh-5,
                       imgui.get_color_u32_rgba(1, 1, 0, 1), '%g Hz'%fps_min )
    draw_list.add_text(winPos[0], winPos[1]-5,
                       imgui.get_color_u32_rgba(1, 1, 0, 1), '%g Hz' % fps_max)
    imgui.end_child()
    imgui.end()

    # ret,self._buffer_frame = self.cam.read()
    self.camera1.SnapImage()
    self.cam_buffer1 = self.camera1.GetImage()
    self.camera2.SnapImage()
    self.cam_buffer2 = self.camera2.GetImage()
    if self.rec_on:
        self.vidwriter.write(np.hstack([self.cam_buffer1,self.cam_buffer2]))

    self.cam_buffer1 = self.cam_buffer1/255.
    self.cam_buffer2 =  self.cam_buffer2/255.




    # fbo_ratio = self._buffer_frame.shape[0]/self._buffer_frame.shape[1]
    # if not self._has_pop:
    imgui.begin("Camera", True)
    imgui.begin_child("Cam 1",480,360)
    imgui.text("Cam 1")
    ww, wh = imgui.get_window_size()
    winPos = imgui.get_cursor_screen_pos()
    # mov_player_pos = self.mov_player['a_pos'].view(dtype=np.float32).reshape(-1,2)
    # mov_player_pos = [1.,ww/wh]
    self.clear()
    self._framebuffer.activate()
    self.dispatch_event("on_draw", .0)
    self._framebuffer.deactivate()
    draw_list = imgui.get_window_draw_list()
    draw_list.add_image(self._framebuffer.color[0]._handle, tuple(winPos), tuple([winPos[0] + ww, winPos[1] + wh]),
                        (0, 0), (1, 1))
    imgui.end_child()


    imgui.same_line()

    imgui.begin_child("Cam 2",480, 360)
    imgui.text("Cam 2")
    ww, wh = imgui.get_window_size()
    winPos = imgui.get_cursor_screen_pos()
    self.clear()
    self._framebuffer2.activate()
    self.dispatch_event("on_draw", .0)
    self._framebuffer2.deactivate()
    draw_list = imgui.get_window_draw_list()

    draw_list.add_image(self._framebuffer2.color[0]._handle, tuple(winPos), tuple([winPos[0] + ww, winPos[1] + wh]),
                        (0, 0), (1, 1))
    imgui.end_child()
    imgui.end()


def pop_on_resize(width, height):
    pass
    # self.Shape['u_scale'] = height / width, 1