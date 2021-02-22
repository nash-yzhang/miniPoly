import imgui
from glumpy import gloo, gl
import cv2 as cv
import numpy as np
import bin.chainProcessor as cp

self = None

def snap(vobj):
    ret,rawim = vobj.read()
    if ret == True:
        rawim = cv.flip(rawim, 0)
        rawim = cv.cvtColor(rawim,cv.COLOR_BGR2RGB)
    return rawim

def binarization(img,thre:int=127):
    if not isinstance(thre,int):
        print("Threshold should be integer")
        thre = np.round(thre)
    if thre > 255 or thre < 0:
        print("Invalid binary threshold value (should be between 0-255)")
        thre = 127
    img = cv.cvtColor(img,cv.COLOR_RGB2GRAY)
    _,bwim = cv.threshold(img,thre,255,cv.THRESH_BINARY)
    bwim = np.repeat(bwim[..., np.newaxis], 3, axis=2)
    return bwim

def switch_gui(cpobj:cp): #TODO: Fix here!
    func_called,output_fetched = cpobj.fetch_('all')
    img_process = [i for i in func_called if i]
    imgui.begin('Control')
    temp,self.image_processor_idx = imgui.listbox("List",self.image_processor_idx,img_process)
    selected_func_name = img_process[self.image_processor_idx]
    if selected_func_name:
        kwarg_selected = cpobj._kwarg[selected_func_name]
        for key,val in kwarg_selected.items():
            _,cpobj._kwarg[selected_func_name][key] = imgui.drag_float(key,val)
    imgui.end()
    return img_process

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
    self.vobj = cv.VideoCapture(0)
    self.vobj_running = True
    _,self._visfishimg = self.vobj.read()

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
                    self.vobj.release()
                    self.vobj_running = False
            else:
                should_run, _ = imgui.menu_item(
                    "Start Live", '', False, True
                )
                if should_run:
                    self.vobj.open(0)
                    self.vobj_running = True
            imgui.end_menu()
        imgui.end_main_menu_bar()
    # if self.image_processor_idx >0:
    #     self.image_processor.exc('snap', self.vobj).exc('bwize', self.image_processor.fetch[1], bwize_kwarg)
    if self.vobj_running:
        self.image_processor.clear()
        self.image_processor.exc('snap',self.vobj).exc('bwize',self.image_processor.fetch[1])
    img_process = switch_gui(self.image_processor)
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
    self.vobj.release()
    self.vobj_running = False
