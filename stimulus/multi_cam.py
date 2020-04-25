from bin.glarage import *
from glumpy import gl, gloo
import imgui
import cv2
# import bin.tisgrabber.tisgrabber as IC
import numpy as np
# from pyfirmata import Arduino, util
import serial.tools.list_ports


self = None

class cam_config:
    def __init__(self,fps = 30, exposure = -4, gain = 0.5):
        self.fps = fps
        self.exposure = exposure
        self.gain = gain
        self.toggle_on = False

def prepare():
    shader_folder = '../bin/shaderfile/'
    vertex_shader_fn = 'VS_basic_tex.glsl'
    frag_shader_fn = 'FS_basic_tex.glsl'
    ports = list(serial.tools.list_ports.comports())
    # Arduino_COM_Name = [p[0] for p in ports if 'Arduino' in p.__str__()][0]
    # self.arduino_board = Arduino(Arduino_COM_Name)
    # self.arduino_iterator = util.Iterator(self.arduino_board)
    # self.arduino_iterator.start()

    # self.LED_pin  = self.arduino_board.get_pin('d:11:p')
    # self.LED_power = .1
    # self.arduino_board.analog[0].enable_reporting()
    # self.ardiuno_sig = [0.]

    # Create camera (list of tuple (cam_obj, boolean -> if cam is opened))
    self.camera = []
    self.camera_config = []
    self.camera_isalive = []
    cam_openable = True
    n_cam = 0
    self._cam_VS = load_shaderfile(shader_folder + vertex_shader_fn)
    self._cam_FS = load_shaderfile(shader_folder + frag_shader_fn)

    unit_player = gloo.Program(self._cam_VS, self._cam_FS)
    unit_player.cam_id = len(self.camera)
    unit_player['a_pos'] = [(-1, -1), (-1, +1), (+1, -1), (+1, +1)]
    unit_player['a_texcoord'] = [(0., 0.), (0., 1.), (1., 0.), (1., 1.)]

    self.mov_player = []
    self.cam_buffer = []
    self._framebuffers = []


    while cam_openable:
        temp_cam = cv2.VideoCapture(n_cam)
        cam_openable = temp_cam.read()[0]
        n_cam += 1
        if cam_openable:
            _, unit_buffer = temp_cam.read()
            unit_player['texture'] = unit_buffer
            self.mov_player.append(unit_player)
            self.cam_buffer.append(unit_buffer)
            self._framebuffers.append(gloo.FrameBuffer(color=np.zeros((self.height, self.width, 4), np.float32).view(gloo.Texture2D)))

            self.camera_config.append(cam_config())
            if len(self.camera) > 0: #Display the default cam
                self.camera.append([temp_cam,False])
                temp_cam.release()
            else:
                self.camera.append([temp_cam,True])

    self._clock.set_fps_limit(60)

    self.dtlist = [(0.,0.)]

    self.vid_fn = './/Output1111.avi'
    vidbuffer_shape = np.hstack(self.cam_buffer).shape
    self.vidwriter = cv2.VideoWriter(self.vid_fn, cv2.VideoWriter_fourcc(*'XVID'), 30.,
                                     (int(vidbuffer_shape[1]), int(vidbuffer_shape[0])))
    self.rec_timepoint = []
    self.rec_on = False
    self.rec_button_text = 'Start'
    self._draw_cam = 0


def on_draw(dt):
    # gl.glEnable(gl.GL_DEPTH_TEST)
    self.clear()
    self.mov_player[self._draw_cam]['texture'] = self.cam_buffer[self._draw_cam]
    self.mov_player[self._draw_cam].draw(gl.GL_TRIANGLE_STRIP)

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
                vidbuffer_shape = np.hstack(self.cam_buffer).shape
                self.vidwriter = cv2.VideoWriter(self.vid_fn, cv2.VideoWriter_fourcc(*'XVID'), 30.,
                                                 (int(vidbuffer_shape[1]),int(vidbuffer_shape[0])))
                self.rec_button_text = 'Stop'
    # _,self.LED_power = imgui.slider_float('LED power', self.LED_power, 0.0, 1.0, '%.2f', 1.0)
    # self.LED_pin.write(self.LED_power)

    imgui.listbox_header("", 200, 100)

    for idx in range(len(self.camera)):
        cam_idx = "Cam %d" % idx
        _, self.camera[idx][1] = imgui.selectable(cam_idx, self.camera[idx][1])
        if self.camera[idx][1] and not self.camera[idx][0].read()[0]:
            self.camera[idx][0].open(idx)
        elif self.camera[idx][0].read()[0] and not self.camera[idx][1]:
            self.camera[idx][0].release()

    imgui.listbox_footer()
    imgui.same_line()

    imgui.begin_child("fps plot", 0.,0.)
    ww,wh = imgui.get_window_size()
    wh *=.7
    winPos = imgui.get_cursor_screen_pos()
    winPos = (winPos[0],winPos[1]+30)
    line_st = int(min(max([len(self.dtlist)-ww+x_offset,0]),len(self.dtlist)-1))

    dtlist_adapted = np.array(self.dtlist)[line_st:]
    # dtlist_adapted[:, 0] -= line_st*2
    dtlist_adapted[:,1] = (1-(dtlist_adapted[:,1]-fps_min)/(fps_max-fps_min))*wh
    # try:
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

    if self.rec_on:
        self.vidwriter.write(np.hstack(self.cam_buffer))

    self.dispatch_event("live_view")

def live_view():
    imgui.begin("Camera", True)
    draw_list = imgui.get_window_draw_list()

    # TODO: Somehow the performace drop drasically after adding camera. Need to fix that
    for iter_idx, unit_player in enumerate(self.mov_player):
        if self.camera[iter_idx][1]:
            _, self.cam_buffer[iter_idx] = self.camera[iter_idx][0].read()
            child_name = "cam %d" % iter_idx
            imgui.begin_child(child_name, 480, 360)
            imgui.text(child_name)
            ww, wh = imgui.get_window_size()
            winPos = imgui.get_cursor_screen_pos()
            self._draw_cam = iter_idx
            self.clear()
            self._framebuffers[iter_idx].activate()
            self.dispatch_event("on_draw", .0)
            self._framebuffers[iter_idx].deactivate()
            draw_list.add_image(self._framebuffers[iter_idx].color[0]._handle, tuple(winPos),
                                tuple([winPos[0] + ww, winPos[1] + wh]),
                                (0, 0), (1, 1))
            imgui.end_child()
            imgui.same_line()

    imgui.new_line()
    imgui.new_line()
    for iter_idx, unit_player in enumerate(self.mov_player):
        if self.camera[iter_idx][1]:
            config_name = "Config Cam %d" % iter_idx
            self.camera_config[iter_idx].toggle_on, _ = imgui.collapsing_header(config_name, True)
            if self.camera_config[iter_idx].toggle_on:
                _, buffer_fps = imgui.slider_int('FPS', self.camera_config[iter_idx].fps, 1, 100, '%d')
                if buffer_fps != self.camera_config[iter_idx].fps:
                    self.camera[iter_idx][0].set(cv2.CAP_PROP_FPS, buffer_fps)
                    self.camera_config[iter_idx].fps = buffer_fps
                _, buffer_exposure = imgui.slider_int('Exposure Time', self.camera_config[iter_idx].exposure, -13, -1, '%d')
                if buffer_exposure != self.camera_config[iter_idx].exposure:
                    self.camera[iter_idx][0].set(cv2.CAP_PROP_EXPOSURE, buffer_exposure)
                    self.camera_config[iter_idx].exposure = buffer_exposure
                _, buffer_gain = imgui.slider_float('gain', self.camera_config[iter_idx].gain, 0., 1., '%.2f',1.0)
                if buffer_gain != self.camera_config[iter_idx].gain:
                    self.camera[iter_idx][0].set(cv2.CAP_PROP_GAIN, buffer_gain)
                    self.camera_config[iter_idx].gain = buffer_gain


    imgui.end()

def config_cam(cam_id):
    imgui.begin('config window')
    imgui.end()


def terminate():
    # self.arduino_board.exit()
    for cam in [i for (i, v) in zip(self.camera, self.camera_isalive) if v]:
        cam.release()


def pop_on_resize(width, height):
    pass
    # self.Shape['u_scale'] = height / width, 1