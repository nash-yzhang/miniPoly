import imgui
from glumpy import gloo, gl
import cv2 as cv
import numpy as np
import bin.tisgrabber.tisgrabber as IC
import bin.chainProcessor as cp

self = None

def snap(vobj):
    vobj.SnapImage()
    rawim = vobj.GetImage()
    return rawim

def binarization(img,thre=127):
    _,bwim = cv.threshold(img,thre,255,cv.THRESH_BINARY)
    return bwim

def prepare():
    """
    Initialize the vertex/fragment shader
    """
    self._clock.set_fps_limit(50)
    vertex_2 = """
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

    fragment_2 = """
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
    self._visfishimg = self.vobj.GetImage()
    self._program2 = gloo.Program(vertex_2, fragment_2)
    self._program2.bind(self.V2)
    self._program2['texture'] = self._visfishimg
    self._program2['texture'].wrapping = gl.GL_REPEAT
    self._program2['aspect'] = [1, 1]

    self.image_processor = cp.chainProcessor(10)
    self.image_processor.reg('snap',snap)
    self.image_processor.reg('bwize',binarization)
    self.image_processor_idx = 0

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
    self.image_processor.clear()
    _,bwize_kwarg = self.image_processor.get_arg('bwize')
    self.image_processor.exc('snap',self.vobj).exc('bwize',self.image_processor.fetch[1],thre=bwize_kwarg['thre'])
    img_process,_ = self.image_processor.fetch_('all')
    img_process = [i for i in img_process if i]
    imgui.begin('Control')
    temp,self.image_processor_idx = imgui.listbox("List",self.image_processor_idx,img_process)
    imgui.text("Frame duration: %.2f ms" % (self.dt * 1000))
    imgui.text("FPS: %d Hz" % round(1 / (self.dt + 1e-8)))
    imgui.end()
    # if self.image_processor_idx >0:
    #     self.image_processor.exc('snap', self.vobj).exc('bwize', self.image_processor.fetch[1], bwize_kwarg)

    _,self._visfishimg = self.image_processor.fetch_(self.image_processor_idx+len(self.image_processor._output)-len(img_process))
    imgui.begin("VisFish", True)  # , flags = imgui.WINDOW_NO_TITLE_BAR)
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