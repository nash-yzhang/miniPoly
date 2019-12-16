from glumpy import app, gl, glm, gloo
from glumpy.app import configuration
from glumpy.app.window import Window
from functools import wraps # This convenience func preserves name and docstring

from IPython import embed

def add_method(cls):
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            return func(*args, **kwargs)
        setattr(cls, func.__name__, wrapper)
        # Note we are not binding func, but wrapper which accepts self but does exactly the same as func
        return func # returning func means func can still be used normally
    return decorator
#%
class stiObj():
    def __init__(self, *args, **kwargs) :
        config = configuration.get_default()
        if "config" not in kwargs.keys():
            kwargs['config'] = config
        if "backend" not in kwargs.keys():
            kwargs['backend'] = "qt5"
        backendname = kwargs.pop('backend')
        self._backend = app.use(backendname)
        self.window = app.Window(*args,**kwargs)
        self.window._buffer = {}
        self.window._program = []
        self.on_draw = self.window.event(self.on_draw)
        self.on_resize = self.window.on_resize
        self.on_init = self.window.on_init

    @property
    def Program(self) :
        return self.window._program

    @Program.setter
    def Program(self, args) :
        if len (self.window._program) > 0 :
            self.window._program.append (gloo.Program (*args))
        else :
            self.window._program = [gloo.Program (*args)]


    @property
    def Buffer(self) :
        return self.window._buffer

    @Buffer.setter
    def Buffer(self, arg_dict):
        self.window._buffer.update(arg_dict)

    def on_draw(self,dt):
        self.window.clear()
        gl.glDisable (gl.GL_BLEND)
        gl.glEnable (gl.GL_DEPTH_TEST)
        print(dt)
        motmat_x_R = self.window._buffer['motmat_ang'][0]
        motmat_y_R = self.window._buffer['motmat_ang'][1]
        motmat_R = cen2square (np.array ([motmat_x_R])[None, :], np.array ([motmat_y_R])[None, :],
                               np.array ([motmat_y_R])[None, :] * 0).reshape ([-1, 2])
        self.window._program[0]['texcoord'] += motmat_R[self.window._buffer["textface"]] / 300
        self.window._program[0].draw (gl.GL_TRIANGLES, self.window._buffer['I'])
# %
import numpy as np
from scipy import signal
from sklearn.decomposition import PCA

vertex = """
uniform mat4   model;      // Model matrix
uniform mat4   view;       // View matrix
uniform mat4   projection; // Projection matrix
attribute vec2 position;   // Vertex position
attribute vec2 texcoord;   // Vertex texture coordinates red
varying vec2   v_texcoord;   // Interpolated fragment texture coordinates (out)
//attribute vec2 texcoord_G;   // Vertex texture coordinates red
//varying vec2   v_texcoord_G;   // Interpolated fragment texture coordinates (out)
//attribute vec2 texcoord_B;   // Vertex texture coordinates red
//varying vec2   v_texcoord_B;   // Interpolated fragment texture coordinates (out)

void main()
{
    // Assign varying variables
    v_texcoord  = texcoord;

    // Final position
    gl_Position = projection * view * model * vec4(position,0.0,1.0);
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

def cen2square(cen_x=np.array ([0]), cen_y=np.array ([0]), square_size=np.array ([1])) :
    square_r = square_size / 2
    squarePoint = np.array ([[cen_x - square_r, cen_y - square_r],
                             [cen_x - square_r, cen_y + square_r],
                             [cen_x + square_r, cen_y + square_r],
                             [cen_x + square_r, cen_y - square_r]])
    return squarePoint
def patchArray(imgsize=np.array ([1, 1]), startpoint=np.array ([[0, 0], [0, 1], [1, 1], [1, 0]])) :
    vtype = [('position', np.float32, 2),
             ('texcoord', np.float32, 2)]
    itype = np.uint32
    imgvertice = np.array ([np.arange (imgsize[0] + 1)]).T + \
                 np.array ([np.arange (imgsize[1] + 1) * 1.j])
    adding_idx = np.arange (imgvertice.size).reshape (imgvertice.shape)

    # Vertices positions
    p = np.stack ((np.real (imgvertice.flatten ()), \
                   np.imag (imgvertice.flatten ())), axis=-1)

    imgV_conn = np.array ([[0, 1, imgvertice.shape[1], 1, imgvertice.shape[1], imgvertice.shape[1] + 1]],
                          dtype=np.uint32) + \
                np.array ([adding_idx[0 :-1, 0 :-1].flatten ()], dtype=itype).T
    faces_t = np.resize (np.array ([1, 0, 2, 0, 2, 3], dtype=itype), imgsize.prod () * 6)
    faces_t += np.repeat (np.arange (imgsize.prod (), dtype=itype) * 4, 6)
    vertices = np.zeros (imgV_conn.size, vtype)
    vertices['position'] = p[imgV_conn.flatten ()]
    vertices['texcoord'] = startpoint[faces_t]

    filled = np.arange (imgV_conn.size, dtype=itype)

    vertices = vertices.view (gloo.VertexBuffer)
    filled = filled.view (gloo.IndexBuffer)

    return vertices, filled, faces_t

patchArray_size = np.array ([1, 1])
startpoint = cen2square (np.random.rand (patchArray_size.prod ()),
                         np.random.rand (patchArray_size.prod ()),
                         np.ones (patchArray_size.prod ()) / 10).reshape ([-1, 2])
motmat_ang = [1, 0]
motmat_x_R = motmat_ang[0]
motmat_y_R = motmat_ang[1]
V, I, textface = patchArray (patchArray_size, startpoint)
#%
a = stiObj()
a.Buffer = {"I" : I, "motmat_ang" : motmat_ang}
a.Buffer = {"textface": textface}
#%
a.Program = vertex, fragment
workingProgram = a.Program[0]
workingProgram.bind (V)
workingProgram['texture'] = np.uint8 (np.round ((np.random.rand (100, 100, 1) > .5) * 155 + 100) * np.array ([[[1, 1, 1]]]))
workingProgram['texture'].wrapping = gl.GL_REPEAT
workingProgram['model'] = np.eye (4, dtype=np.float32)
workingProgram['view'] = glm.translation (*patchArray_size * -.5, -2)

a.window.activate()
a.on_init()
a.on_resize(a.window.width,a.window.height)
app.run()
#%%
a.window.on_resize(a.window.width,a.window.height)
a.on_draw()
a.window.dispatch_event("on_init")
a.window.dispatch_event("on_resize",a.window.width,a.window.height)
a.window.dispatch_event("on_draw",0.0)
#%%
@a.window.event
def on_init():
    print('Initialization')

