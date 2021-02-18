import imgui
from glumpy import gloo, gl
import cv2 as cv
import numpy as np
import bin.tisgrabber.tisgrabber as IC
from sklearn.decomposition import PCA

self = None


def longaxis(bwim, pca):
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
    head = cenpoint[::-1] + np.max(body_axis_score) * body_axis_vector[::-1]
    tail = cenpoint[::-1] + np.min(body_axis_score) * body_axis_vector[::-1]
    # head = pix_coord[np.argmin(body_axis_score), ::-1]
    # tail = pix_coord[np.argmax(body_axis_score), ::-1]
    return np.vstack([head, tail])


def prepare():
    """
    Initialize the vertex/fragment shader
    """
    self._clock.set_fps_limit(50)

    vertex = """
       uniform vec2 aspect;
       attribute vec2 position;   // Vertex position

       void main()
       {
           gl_Position = vec4(aspect*position,0.0,1.0);
       }
       """

    fragment = """
        # define PI 3.14159265
        uniform vec2 u_resolution;
        uniform float u_time;
        uniform float pat_scale;
        uniform float speed;
        uniform float dir;
        void main() {
            vec2 st = gl_FragCoord.xy/u_resolution.xy;
            st.x *= u_resolution.x/u_resolution.y;
            st -= 0.5;
            float stepthre = 0.224;
            mat2 rot_mat = mat2(cos(dir), sin(dir), -sin(dir), cos(dir));
            st = rot_mat*st;
            vec2 mov_pat = vec2(1.,0.)*u_time*speed;
            float pat_c = 0.;smoothstep(stepthre+.1,stepthre,distance(fract(st*pat_scale+vec2(0.610,0.470)),vec2(.5)))*step(0.5,sin(u_time*20.));
            float pat_b = smoothstep(stepthre,stepthre+.1,distance(fract(st*pat_scale-mov_pat),vec2(.5)));
            float pat_a = smoothstep(stepthre,stepthre+.1,distance(fract(st*pat_scale+mov_pat),vec2(.5)));
            gl_FragColor = vec4(vec3(pat_a+pat_b)/2.,1.0);
        }
       """
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
    V2["texcoord"] = [[0., 0.], [0., 1.], [1., 0.], [1., 1.]]
    self.V2 = V2.view(gloo.VertexBuffer)
    self.speed = 0.01
    self.dir = 0.
    self.adddir = 0.
    self.pat_scale = 1.
    self._program = gloo.Program(vertex, fragment)
    self._program['position'] = [[-1, -1], [1, -1], [-1, 1], [1, 1]]
    self._program['u_time'] = 0.
    self._program['u_resolution'] = (512, 512)
    self._program['aspect'] = [1., 1.]
    self._program['pat_scale'] = self.pat_scale
    self._program['speed'] = self.speed
    self._program['dir'] = self.adddir

    # Setup the camera streaming
    self.vobj = IC.TIS_CAM()
    self.vobj.DevName = self.vobj.GetDevices()[0].decode("utf-8")
    self.vobj.open(self.vobj.DevName)
    self.vobj.SetVideoFormat("Y16 (752x480)")
    self.vobj.SetContinuousMode(0)
    self.vobj.StartLive(0)
    self.vobj.SnapImage()
    self._visfishimg = self.vobj.GetImage()
    self._program2 = gloo.Program(vertex_2, fragment_2)
    self._program2.bind(self.V2)
    self._program2['texture'] = self._visfishimg
    self._program2['texture'].wrapping = gl.GL_REPEAT
    self._program2['aspect'] = [1, 1]

    self._texture_buffer2 = np.zeros((self.height, self.width, 4), np.float32).view(gloo.Texture2D)
    self._framebuffer2 = gloo.FrameBuffer(color=[self._texture_buffer2])

    self.x_crop = 0
    self.y_crop = 45
    self.segthre = 24
    self.ybound = np.array([100, 600])
    self.xbound = np.array([0, 500])
    self.sizebound = [50, 150]
    self._pca = PCA(n_components=2)
    self._framecount = 0
    self._ba = None
    if self._name == 'main':
        self.init_pop_process()


def set_widgets():

    self.vobj.SnapImage()
    rawim = self.vobj.GetImage()
    try:
        imslice = 255-rawim[self.xbound[0]:self.xbound[1], self.ybound[0]:self.ybound[1], 0]
        th2 = 255 - cv.adaptiveThreshold(imslice, 255, cv.ADAPTIVE_THRESH_MEAN_C, cv.THRESH_BINARY, self.y_crop * 2 + 1,
                                         self.segthre)
        _, labels = cv.connectedComponents(th2)
        labelC = np.bincount(labels.flatten())
        sizebound = self.sizebound
        idx = [i for i, x in enumerate(labelC) if ((x > sizebound[0]) & (x <= sizebound[1]))]
        th3 = np.isin(labels, idx)
        body_axis = longaxis(th3, self._pca)
        body_ori = body_axis[0] - body_axis[1]
        body_ori = body_ori[1] + 1j * body_ori[0]
        if self._ba:
            balength_diff = np.abs(np.abs(body_ori) - np.abs(self._ba))
        else:
            balength_diff = 0
            self._ba = body_ori
        body_ori /= np.abs(body_ori)
        buffer_ori = np.exp(1j*self.dir)
        buffer_ori = np.real(buffer_ori)*1j+np.imag(buffer_ori)
        buffer_ori_diff = np.abs(np.imag(np.log(buffer_ori/body_ori)))
        if buffer_ori_diff>np.pi/9 and balength_diff<50:
            self.dir = np.imag(np.log(body_ori)) + self.adddir
            self._ba = body_ori
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
        self._visfishimg = cv.line(rawim, tuple(botheye[0] + loc_cor), tuple(botheye[1] + loc_cor), (255, 0, 0),
                                   thickness=2)
    except:
        self._visfishimg = rawim
        self.ybound = np.array([0, rawim.shape[0]])
        self.xbound = np.array([0, rawim.shape[1]])
        # self.sizebound = [50, 150]

    imgui.begin("Custom window", True)
    _, self.adddir = imgui.slider_float("Direciton", self.adddir, -np.pi, np.pi)
    _, self.speed = imgui.drag_float("Speed", self.speed, 0.1)
    _, self.pat_scale = imgui.drag_float("pat_scale", self.pat_scale, 0.1)
    _, self.sizebound[0] = imgui.slider_float("sizebound_lower", self.sizebound[0], 10, 500)
    _, self.sizebound[1] = imgui.slider_float("sizebound_upper", self.sizebound[1], 11, 501)
    _, self.y_crop = imgui.slider_float("block size", self.y_crop, 0, 100)
    self.y_crop = np.round(self.y_crop).astype(int)
    _, self.segthre = imgui.slider_float("threshold", self.segthre, 0, 255)
    imgui.text("FPS: %d" % (1 / (self.dt + 1e-5)))
    imgui.end()

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
        self.minion_plug.put(self, ['dir', 'speed', 'pat_scale'])
        self.minion_plug.give(self._children, ['dir', 'speed', 'pat_scale'])


def on_init():
    gl.glEnable(gl.GL_DEPTH_TEST)


def draw(ww, wh):
    self.clear()
    _aspect = [ww / max(ww, wh), wh / max(ww, wh)]
    self._program['u_resolution'] = (ww, wh)
    self._program['u_time'] += self.dt
    self._program['aspect'] = _aspect[::-1]
    self._program['pat_scale'] = self.pat_scale
    self._program['speed'] = self.speed
    self._program['dir'] = self.dir
    self._program.draw(gl.GL_TRIANGLE_STRIP)


def draw2(ww, wh):
    self.clear()
    _aspect = [ww / max(ww, wh), wh / max(ww, wh)]
    self._program2['aspect'] = _aspect[::-1]
    self._program2['texture'] = self._visfishimg
    self._program2.draw(gl.GL_TRIANGLE_STRIP)


def client_draw():
    self.minion_plug.get(self._parent)
    self.__dict__.update(self.minion_plug.fetch({'dir': 'dir', 'speed': 'speed', 'pat_scale': 'pat_scale'}))
    ww, wh = self._width, self._height
    self.dispatch_event('draw', ww, wh)

def terminate():
    self.vobj.StopLive()