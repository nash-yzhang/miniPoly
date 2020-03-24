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

    self.arduino_board = Arduino('COM7')
    self.arduino_iterator = util.Iterator(self.arduino_board)
    self.arduino_iterator.start()

    self.LED_pin  = self.arduino_board.get_pin('d:11:p')
    self.LED_power = .1
    # self.arduino_board.analog[0].enable_reporting()
    # self.ardiuno_sig = [0.]
    self.camera = []
    self.camera_isalive = []
    cam_opened = True
    n_cam = 0
    while cam_opened:
        temp_cam = cv2.VideoCapture(n_cam)
        cam_opened = temp_cam.read()[0]
        if cam_opened:
            self.camera.append(temp_cam)
            n_cam += 1
            if n_cam > 1: #Display the default cam
                self.camera_isalive.append(False)
                temp_cam.release()
            else:
                self.camera_isalive.append(True)


    self._clock.set_fps_limit(30)
    # Our operations on the frame come here

    self._cam_VS = load_shaderfile(shader_folder + vertex_shader_fn)
    self._cam_FS = load_shaderfile(shader_folder + frag_shader_fn)

    self.mov_player = []
    self.cam_buffer = []
    self.additional_framebuffer = []
    for cam_id in range(len(self.camera)):
        if self.camera_isalive[cam_id]:
            cam = self.camera[cam_id]
            unit_player = gloo.Program(self._cam_VS, self._cam_FS)
            unit_player.cam_id = cam_id
            unit_player['a_pos'] = [(-1,-1), (-1,+1), (+1,-1), (+1,+1)]
            unit_player['a_texcoord'] = [(0.,0.), (0.,1.), (1.,0.), (1.,1.)]
            _,unit_buffer = cam.read()
            unit_player['texture'] = unit_buffer
            self.mov_player.append(unit_player)
            self.cam_buffer.append(unit_buffer)
            if len(self.mov_player)>1:
                self.additional_framebuffer.append(gloo.FrameBuffer(color=np.zeros((self.height, self.width, 4), np.float32).view(gloo.Texture2D)))


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
    self._draw_cam += 1

def set_widgets():
    fps_min = 15.
    fps_max = 45.
    x_offset = 50.
    # self.ardiuno_sig.append(self.arduino_board.analog[0].read())
    # print(self.ardiuno_sig[-1])
    self.dtlist.append((len(self.dtlist),1/max([self.dt,0.0001])))

    imgui.begin("Example: custom listbox")

    imgui.listbox_header("", 200, 100)

    for idx in range(len(self.camera_isalive)):
        cam_idx = "Cam %d"%idx
        _,self.camera_isalive[idx] = imgui.selectable(cam_idx, self.camera_isalive[idx])
        if self.camera_isalive[idx] and not self.camera[idx].read()[0]:
            self.camera[idx].open(idx)
        elif self.camera[idx].read()[0] and not self.camera_isalive[idx]:
            self.camera[idx].release()

    imgui.listbox_footer()
    imgui.end()
    for cam_id in range(len(self.camera)):
        if self.camera_isalive[cam_id]:
            if all(ii.cam_id != cam_id for ii in self.mov_player): #TODO: FNIALIZE HERE
                cam = self.camera[cam_id]
                unit_player = gloo.Program(self._cam_VS, self._cam_FS)
                unit_player.cam_id = cam_id
                unit_player['a_pos'] = [(-1,-1), (-1,+1), (+1,-1), (+1,+1)]
                unit_player['a_texcoord'] = [(0.,0.), (0.,1.), (1.,0.), (1.,1.)]
                _,unit_buffer = cam.read()
                unit_player['texture'] = unit_buffer
                self.mov_player.append(unit_player)
                self.cam_buffer.append(unit_buffer)
                if len(self.mov_player)>1:
                    self.additional_framebuffer.append(gloo.FrameBuffer(color=np.zeros((self.height, self.width, 4), np.float32).view(gloo.Texture2D)))

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

    imgui.begin("Camera", True)
    self._draw_cam = 0
    draw_list = imgui.get_window_draw_list()

    #TODO: sort out the indexing system for camera camera_isalive movplayer cam_buffer framebuffer, now is a mess
    #TODO: Somehow the performace drop drasically after adding camera. Need to fix that
    #TODO: Add saving system
    for iter_idx, unit_player in enumerate(self.mov_player):
        if self.camera_isalive[iter_idx]:
            _, self.cam_buffer[iter_idx] = self.camera[unit_player.cam_id].read()
            child_name = "cam %d"%unit_player.cam_id
            imgui.begin_child(child_name,480,360)
            imgui.text(child_name)
            ww, wh = imgui.get_window_size()
            winPos = imgui.get_cursor_screen_pos()
            self.clear()
            if iter_idx>0:
                self.additional_framebuffer[iter_idx-1].activate()
                self.dispatch_event("on_draw", .0)
                self.additional_framebuffer[iter_idx-1].deactivate()
                draw_list.add_image(self.additional_framebuffer[iter_idx-1].color[0]._handle, tuple(winPos), tuple([winPos[0] + ww, winPos[1] + wh]),
                                (0, 0), (1, 1))
            else:
                self._framebuffer.activate()
                self.dispatch_event("on_draw", .0)
                self._framebuffer.deactivate()
                draw_list.add_image(self._framebuffer.color[0]._handle, tuple(winPos), tuple([winPos[0] + ww, winPos[1] + wh]),
                                (0, 0), (1, 1))

            imgui.end_child()
            imgui.same_line()

    imgui.end()

def close():
    self.arduino_board.exit()
    for cam in [i for (i, v) in zip(self.camera, self.camera_isalive) if v]:
        cam.release()


def pop_on_resize(width, height):
    pass
    # self.Shape['u_scale'] = height / width, 1