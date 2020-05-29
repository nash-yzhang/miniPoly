# -----------------------------------------------------------------------------
# Python and OpenGL for Scientific Visualization
# www.labri.fr/perso/nrougier/python+opengl
# Copyright (c) 2017, Nicolas P. Rougier
# Distributed under the 2-Clause BSD License.
# -----------------------------------------------------------------------------
import numpy as np
from scipy import signal
from glumpy import gl, glm, gloo
import imgui

static_func_name = ['cen2square','patchArray']
self = None

def cen2square(cen_x=np.array([0]), cen_y=np.array([0]), square_size=np.array([1])):
    square_r = square_size / 2
    squarePoint = np.array([[cen_x - square_r, cen_y - square_r],
                            [cen_x - square_r, cen_y + square_r],
                            [cen_x + square_r, cen_y + square_r],
                            [cen_x + square_r, cen_y - square_r]])
    return squarePoint.transpose([2, 0, 1])


def patchArray(imgsize=np.array([1, 1]), startpoint=np.array([[0, 0], [0, 1], [1, 1], [1, 0]])):
    vtype = [('position', np.float32, 2),
             ('texcoord', np.float32, 2)]
    itype = np.uint32
    imgvertice = np.array([np.arange(imgsize[0] + 1)]).T + \
                 np.array([np.arange(imgsize[1] + 1) * 1.j])
    imgvertice /= max(imgsize)/2
    imgvertice -= np.mean(imgvertice)
    adding_idx = np.arange(imgvertice.size).reshape(imgvertice.shape)

    # Vertices positions
    p = np.stack((np.real(imgvertice.flatten()), \
                  np.imag(imgvertice.flatten())), axis=-1)

    imgV_conn = np.array([[0, 1, imgvertice.shape[1], 1, imgvertice.shape[1], imgvertice.shape[1] + 1]],
                         dtype=np.uint32) + \
                np.array([adding_idx[0:-1, 0:-1].flatten()], dtype=itype).T
    faces_t = np.resize(np.array([1, 0, 2, 0, 2, 3], dtype=itype), imgsize.prod() * 6)
    faces_t += np.repeat(np.arange(imgsize.prod(), dtype=itype) * 4, 6)
    vertices = np.zeros(imgV_conn.size, vtype)
    vertices['position'] = p[imgV_conn.flatten()]
    vertices['texcoord'] = startpoint[faces_t]

    filled = np.arange(imgV_conn.size, dtype=itype)

    vertices = vertices.view(gloo.VertexBuffer)
    filled = filled.view(gloo.IndexBuffer)

    return vertices, filled, faces_t

def prepare():
    self._clock.set_fps_limit(50)
    vertex = """
    //uniform mat4   projection; // Projection matrix
    attribute vec2 position;   // Vertex position
    attribute vec2 texcoord;   // Vertex texture coordinates red
    varying vec2   v_texcoord;   // Interpolated fragment texture coordinates (out)
    
    void main()
    {
        // Assign varying variables
        v_texcoord  = texcoord;
    
        // Final position
        gl_Position = vec4(position,0.0,1.0);
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
    patchArray_size = np.array([100, 100])
    startpoint = cen2square(np.random.rand(patchArray_size.prod()),
                            np.random.rand(patchArray_size.prod()),
                            np.ones(patchArray_size.prod()) / 10).reshape([-1, 2])
    # first build the smoothing kernel
    sigma = .8  # width of kernel
    x = np.linspace(-10, 10, 50)  # coordinate arrays -- make sure they contain 0!
    y = np.linspace(-10, 10, 50)
    z = np.linspace(-10, 10, 50)
    xx, yy, zz = np.meshgrid(x, y, z)
    kernel = np.exp(-(xx ** 2 + yy ** 2 + zz ** 2) / (2 * sigma ** 2))

    motmat_angle = np.exp(np.random.rand(*patchArray_size, 100) * 2.j * np.pi)
    self.motmat_x = signal.convolve(motmat_angle.real, kernel, mode='same').reshape(patchArray_size.prod(), -1)
    self.motmat_y = signal.convolve(motmat_angle.imag, kernel, mode='same').reshape(patchArray_size.prod(), -1)

    self.V, self.I, self.textface = patchArray(patchArray_size, startpoint)
    self.patchMat = gloo.Program(vertex, fragment)
    self.patchMat.bind(self.V)
    self.patchMat['texture'] = np.uint8(np.round((np.random.rand(100, 100, 1) > .9) * 155 + 100) * np.array([[[1, 1, 1]]]))
    self.patchMat['texture'].wrapping = gl.GL_REPEAT
    self.time = 0
    self.logspeed = 0
    self.texscale = 1
    self.arc_texcoord = self.V['texcoord'];

def draw(ww,wh):
    self.clear((0,0,0,1))
    # gl.glDisable(gl.GL_BLEND)
    # gl.glEnable(gl.GL_DEPTH_TEST)
    tidx = np.mod(self.time,99)
    motmat = cen2square(self.motmat_x[:,tidx],self.motmat_y[:,tidx],self.motmat_x[:,tidx]*0).reshape([-1,2])
    self.V['texcoord'] = (self.arc_texcoord+motmat[self.textface] * np.exp(self.logspeed)) * self.texscale
    self.arc_texcoord = self.V['texcoord']/self.texscale
    # self.patchMat['view'] = glm.translation(self.x_shift, self.y_shift, self.z_shift)
    self.patchMat.draw(gl.GL_TRIANGLES, self.I)
    self.time+=1

def set_widgets():
    imgui.begin('FPS')
    imgui.text("Frame duration: %.2f ms" %(self.dt*1000))
    imgui.text("FPS: %d Hz"%round(1/(self.dt+1e-8)))
    _, self.logspeed = imgui.slider_float("Log(Speed)", self.logspeed, -10, 10)
    _, self.texscale = imgui.slider_float("Texture scale", self.texscale, 0.01, 2)
    imgui.end()

    imgui.begin("GLView", True)#, flags = imgui.WINDOW_NO_TITLE_BAR)
    ww, wh = imgui.get_window_size()
    winPos = imgui.get_cursor_screen_pos()
    self.clear()
    self._framebuffer.activate()
    self.dispatch_event('draw',ww,wh)
    self._framebuffer.deactivate()
    draw_list = imgui.get_window_draw_list()
    draw_list.add_image(self._framebuffer.color[0]._handle, tuple(winPos), tuple([winPos[0] + ww, winPos[1] + wh]),
                        (0, 0), (1, 1))
    imgui.end()
