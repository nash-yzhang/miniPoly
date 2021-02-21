import imgui
from glumpy import gloo, gl
import cv2 as cv
import numpy as np
import bin.tisgrabber.tisgrabber as IC
from sklearn.decomposition import PCA

self = None
def longaxis(bwim,pca):
    """
    Detect zebrafish body axis (the long axis of an eclipse)
    :param bwim: binarized image
    :param pca: pca object... need to optimize here
    :return: the column vectors of head and tail positions
    """
    pix_x, pix_y = np.where(bwim)
    pix_coord = np.vstack([pix_x, pix_y]).T
    pca.fit(pix_coord)
    cenpoint = np.mean(pix_coord, axis=0)
    body_axis_vector = pca.components_[0, :]
    body_axis_score = np.sum(body_axis_vector * (pix_coord - cenpoint), axis=1)
    head = cenpoint[::-1]+np.max(body_axis_score)*body_axis_vector[::-1]
    tail = cenpoint[::-1]+np.min(body_axis_score)*body_axis_vector[::-1]
    # head = pix_coord[np.argmin(body_axis_score), ::-1]
    # tail = pix_coord[np.argmax(body_axis_score), ::-1]
    return np.vstack([head,tail])

def prepare():
    """
    Initialize the vertex/fragment shader
    """
    self._clock.set_fps_limit(50)
    vertex = """
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

    fragment = """
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
    self.quad = gloo.Program(vertex, fragment)
    vtype = [('position', np.float32, 2),
             ('texcoord', np.float32, 2)]
    V = np.zeros(4, vtype)
    V["position"] = [[-1., -1.], [-1., 1.], [1., -1.], [1., 1.]]
    V["texcoord"] = [[0., 0.], [0., 1.], [1., 0.], [1., 1.]]
    V["texcoord"] += .5
    V["texcoord"] /= 2
    V2 = np.zeros(4, vtype)
    V2["position"] = [[-1., -1.], [-1., 1.], [1., -1.], [1., 1.]]
    V2["texcoord"] = [[0., 0.], [0., 1.], [1., 0.], [1., 1.]]
    self.V = V.view(gloo.VertexBuffer)
    self.V2 = V2.view(gloo.VertexBuffer)
    self.speed = 0.01
    self.dir = 0
    self.adddir = 0
    self._program = gloo.Program(vertex, fragment)
    self._program.bind(self.V)
    self._program['texture'] = np.uint8(np.round((np.random.rand(100, 100, 1) > .9) * 155+100) * np.array([[[1, 1, 1]]]))
    self._program['texture'].wrapping = gl.GL_REPEAT
    self._program['aspect'] = [1,1]

    # Setup the camera streaming
    self.vobj = IC.TIS_CAM()
    self.vobj.DevName = self.vobj.GetDevices()[0].decode("utf-8")
    self.vobj.open(self.vobj.DevName)
    self.vobj.SetVideoFormat("Y16 (752x480)")
    self.vobj.SetContinuousMode(0)
    self.vobj.StartLive(0)
    self.vobj.SnapImage()
    self._visfishimg = self.vobj.GetImage()
    self._program2 = gloo.Program(vertex, fragment)
    self._program2.bind(self.V2)
    self._program2['texture'] = self._visfishimg
    self._program2['texture'].wrapping = gl.GL_REPEAT
    self._program2['aspect'] = [1,1]

    self._texture_buffer2 = np.zeros((self.height, self.width, 4), np.float32).view(gloo.Texture2D)
    self._framebuffer2 = gloo.FrameBuffer(color=[self._texture_buffer2])

    self.x_crop  = 0
    self.y_crop  = 0
    self.segthre = 15
    self.ybound = np.array([100, 600])
    self.xbound = np.array([0, 500])
    self.sizebound = [50, 150]
    self._pca = PCA(n_components=2)
    self._framecount = 0

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


    self.vobj.SnapImage()
    rawim = self.vobj.GetImage()
    # bgim = np.zeros(rawim.shape)
    # bgim[self.x_crop:-self.x_crop-1, -self.y_crop:-self.y_crop-1, :] = rawim[self.x_crop:-self.x_crop-1, -self.y_crop:-self.y_crop-1, :]
    # rawim = rawim[self.x_crop:-self.x_crop-1, -self.y_crop:-self.y_crop-1, :]
    try:
        imslice = rawim[self.xbound[0]:self.xbound[1], self.ybound[0]:self.ybound[1], 0]
        th2 = 255 - cv.adaptiveThreshold(imslice, 255, cv.ADAPTIVE_THRESH_MEAN_C, cv.THRESH_BINARY, self.y_crop*2+1, self.segthre)
        _, labels = cv.connectedComponents(th2)
        labelC = np.bincount(labels.flatten())
        sizebound = self.sizebound
        idx = [i for i, x in enumerate(labelC) if ((x > sizebound[0]) & (x <= sizebound[1]))]
        th3 = np.isin(labels, idx)
        body_axis = longaxis(th3,self._pca)
        body_ori  = body_axis[0]-body_axis[1]
        body_ori = body_ori[1]+1j*body_ori[0]
        self.dir  = np.imag(np.log(body_ori/np.abs(body_ori)))+self.adddir
        botheye = np.round(body_axis).astype(np.int)
        validsize = labelC[(labelC > sizebound[0]) & (labelC <= sizebound[1])]
        self.xbound = np.array(
            [max(min(botheye[:, 1]) - 50 + self.xbound[0], 0),
            min(max(botheye[:, 1]) + 50 + self.xbound[0], rawim.shape[1])])
        self.ybound = np.array(
            [max(min(botheye[:, 0]) - 50 + self.ybound[0], 0),
             min(max(botheye[:, 0]) + 50 + self.ybound[0], rawim.shape[0])])
        # self.sizebound = [min(validsize) - 40, max(validsize) + 40]
        loc_cor = [self.ybound[0], self.xbound[0]]
        self._visfishimg = cv.line(rawim, tuple(botheye[0] + loc_cor), tuple(botheye[1] + loc_cor), (255, 0, 0), thickness=2)
    except:
        self._visfishimg = rawim
        self.ybound = np.array([0, rawim.shape[0]])
        self.xbound = np.array([0, rawim.shape[1]])
        self.sizebound = [50, 150]


    imgui.begin("Custom window", True)
    _, self.adddir = imgui.slider_float("Direciton", self.adddir, -np.pi, np.pi)
    _, self.y_crop = imgui.slider_float("block size", self.y_crop, 0, 100)
    self.y_crop = np.round(self.y_crop).astype(int)
    _, self.segthre = imgui.slider_float("threshold", self.segthre, 0, 255)
    _, self.speed = imgui.slider_float("Speed", self.speed, 0, 0.02)
    imgui.text("FPS: %d"%(1/(self.dt+1e-5)))
    imgui.end()


    # imgui.begin("GLView", True)  # , flags = imgui.WINDOW_NO_TITLE_BAR)
    # ww, wh = imgui.get_window_size()
    # winPos = imgui.get_cursor_screen_pos()
    # self.clear()
    # self._framebuffer.activate()
    # self.dispatch_event('draw', ww, wh)
    # self._framebuffer.deactivate()
    # draw_list = imgui.get_window_draw_list()
    # draw_list.add_image(self._framebuffer.color[0]._handle, tuple(winPos), tuple([winPos[0] + ww, winPos[1] + wh]),
    #                     (0, 0), (1, 1))
    # imgui.end()

    imgui.begin("VisFish", True)  # , flags = imgui.WINDOW_NO_TITLE_BAR)
    ww, wh = imgui.get_window_size()
    winPos = imgui.get_cursor_screen_pos()
    self.clear()
    self._framebuffer2.activate()
    self.dispatch_event('draw2', ww, wh)
    self._framebuffer2.deactivate()
    draw_list = imgui.get_window_draw_list()
    draw_list.add_image(self._framebuffer2.color[0]._handle, tuple(winPos), tuple([winPos[0] + ww, winPos[1] + wh]),
                        (0, 0), (1, 1))
    imgui.end()

    if self._children:
        self.minion_plug.put(self, ['dir', 'speed'])
        self.minion_plug.give(self._children, ['dir', 'speed'])



def on_init():
    gl.glEnable(gl.GL_DEPTH_TEST)

def draw(ww,wh):
    # draw program for client
    self.clear()
    mov_dir = np.exp(1j*self.dir)*self.speed
    self.V['texcoord'] += np.array([np.real(mov_dir),np.imag(mov_dir)])
    _aspect = [ww/max(ww, wh),wh/max(ww, wh)]
    self._program['aspect'] = _aspect[::-1]
    self._program.draw(gl.GL_TRIANGLE_STRIP)

def draw2(ww,wh):
    self.clear()
    _aspect = [ww/max(ww, wh),wh/max(ww, wh)]
    self._program2['aspect'] = _aspect[::-1]
    self._program2['texture'] = self._visfishimg
    self._program2.draw(gl.GL_TRIANGLE_STRIP)

def client_draw():
    self.minion_plug.get(self._parent)
    self.__dict__.update(self.minion_plug.fetch({'dir':'dir','speed':'speed'}))
    ww,wh = self._width,self._height
    self.dispatch_event('draw',ww,wh)

def terminate():
    self.vobj.StopLive()