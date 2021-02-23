import imgui
from glumpy import gloo, gl
import cv2 as cv
import numpy as np
import bin.tisgrabber.tisgrabber as IC
from bin.helper import switch_gui, chainProcessor as cp
from copy import deepcopy
self = None

def snap(vobj):
    vobj.SnapImage()
    rawim = vobj.GetImage()
    return rawim

def delta_binarization(img1,img2,thre = 30,lowerbound = 10, upperbound = 100):
    _,bwim = cv.threshold(cv.absdiff(img1,img2),thre,255,cv.THRESH_BINARY)
    _, labels = cv.connectedComponents(bwim[..., 0])
    labelC = np.bincount(labels.flatten())
    idx = [i for i, x in enumerate(labelC) if ((x > lowerbound) & (x <= upperbound))]
    th3 = np.isin(labels, idx)
    motionimg = np.repeat(th3[...,np.newaxis],3,axis=2)*255
    if th3.any():
        pix_x, pix_y = np.where(th3)
        pix_coord = np.vstack([pix_x, pix_y]).T
        cenpoint = np.mean(pix_coord, axis=0).astype(np.uint16)
        output = cv.rectangle(motionimg, (cenpoint[1] - 5, cenpoint[0] - 5), (cenpoint[1] + 5, cenpoint[0] + 5), (0, 128, 255), -1)
        return output
    else:
        return motionimg

def prepare():
    """
    Initialize the vertex/fragment shader
    """
    self.FPS = 50
    self._clock.set_fps_limit(self.FPS)
    self._vertex_2 = """
       uniform vec2 aspect;
       attribute vec2 position;   // Vertex position
       attribute vec2 texcoord;   // Vertex texture coordinates red
       varying vec2   v_texcoord;   // Interpolated fragment texture coordinates (out)

       void main()
       {
           // Assign varying variables
           v_texcoord  = texcoord;

           // Final position
           gl_Position = vec4(aspect*position,0.0,1.0);
       }
       """

    self._fragment_2 = """
       uniform sampler2D texture;    // Texture
       varying vec2      v_texcoord; // Interpolated fragment texture coordinates (in)
       void main()
       {
           // Final color
           gl_FragColor = texture2D(texture, v_texcoord);
       }
       """
    """
    initialize the rendering program
    """
    vtype = [('position', np.float32, 2),
             ('texcoord', np.float32, 2)]
    V2 = np.zeros(4, vtype)
    V2["position"] = [[-1., -1.], [-1., 1.], [1., -1.], [1., 1.]]
    V2["texcoord"] = [[0., 1.], [0., 0.], [1., 1.], [1., 0.]]
    self.V2 = V2.view(gloo.VertexBuffer)
    self.speed = 0.01
    self.dir = 0.
    self.adddir = 0.
    self.pat_scale = 1.
    # Setup the camera streaming
    self.vobj = IC.TIS_CAM()
    self.vobj.DevName = self.vobj.GetDevices()[0].decode("utf-8")
    self.vobj.open(self.vobj.DevName)
    self.vobj.SetVideoFormat("Y16 (752x480)")
    self.vobj.SetContinuousMode(0)
    self.vobj.StartLive(0)
    self.vobj.SnapImage()
    self.vobj_running = True
    temp = self.vobj.GetImage()
    self._visfishimg = deepcopy(temp)
    self._program2 = gloo.Program(self._vertex_2, self._fragment_2)
    self._program2.bind(self.V2)
    self._program2['texture'] = self._visfishimg
    self._program2['texture'].wrapping = gl.GL_REPEAT
    self._program2['aspect'] = [1, 1]

    self.image_processor = cp(2)
    self.image_processor.reg('snap',snap)
    self.image_processor.reg('bwize',delta_binarization,{'thre': ['int',0,255],'lowerbound': ['int',1,200],'upperbound': ['int',10,500]})
    self.image_GUI_idx = 0
    self.image_processor_idx = 0
    self.image_buffer = None

    self._texture_buffer2 = np.zeros((self.height, self.width, 4), np.float32).view(gloo.Texture2D)
    self._framebuffer2 = gloo.FrameBuffer(color=[self._texture_buffer2])

def set_widgets():
    if imgui.begin_main_menu_bar():
        if imgui.begin_menu("Command", True):
            if self.vobj_running:
                should_stop, _ = imgui.menu_item(
                    "Stop Live", '', False, True
                )
                if should_stop:
                    self.vobj.StopLive()
                    self.vobj_running = False
            else:
                should_run, _ = imgui.menu_item(
                    "Start Live", '', False, True
                )
                if should_run:
                    self.vobj.StartLive(0)
                    self.vobj_running = True
            imgui.end_menu()
        imgui.end_main_menu_bar()
    if self.vobj_running:
        self.image_buffer = self.image_processor.fetch_(0)[1]
        self.image_processor.exc('snap', self.vobj)
        if self.image_buffer is None:
            self.image_buffer = self.image_processor.fetch_()[1]*0
        self.image_processor.exc('bwize', self.image_processor.fetch_()[1],self.image_buffer)
    imgui.begin("Inspetor")
    selected_img, self.image_GUI_idx, self.image_processor_idx = switch_gui(self.image_processor, self.image_GUI_idx, self.image_processor_idx)
    imgui.separator()

    _,self.FPS = imgui.slider_float("FPS",self.FPS,1,500)
    imgui.text("Frame duration: %.2f ms" % (self.dt * 1000))
    imgui.text("FPS: %d Hz" % round(1 / (self.dt + 1e-8)))
    self._clock.set_fps_limit(self.FPS)

    imgui.end()
    if selected_img.shape != self._visfishimg.shape:
        self._program2['texture'] = self._visfishimg
        self._program2['texture'].wrapping = gl.GL_REPEAT
        self._program2['aspect'] = [1, 1]

    self._visfishimg = selected_img
    imgui.begin("VisFish", True)
    ww, wh = imgui.get_window_size()
    winPos = imgui.get_cursor_screen_pos()
    self.clear()
    self._framebuffer2.activate()
    self.dispatch_event('draw', ww, wh)
    self._framebuffer2.deactivate()
    draw_list = imgui.get_window_draw_list()
    draw_list.add_image(self._framebuffer2.color[0]._handle, tuple(winPos), tuple([winPos[0] + ww, winPos[1] + wh]),
                        (0, 0), (1, 1))
    imgui.end()

def draw(ww, wh):
    self.clear()
    img_aspect = self._visfishimg.shape[0]/self._visfishimg.shape[1]
    _aspect = [ww / max(ww, wh)*img_aspect, wh / max(ww, wh)]
    self._program2['aspect'] = _aspect[::-1]
    self._program2['texture'] = self._visfishimg
    self._program2.draw(gl.GL_TRIANGLE_STRIP)

def terminate():
    self.vobj.StopLive()
    self.vobj_running = False