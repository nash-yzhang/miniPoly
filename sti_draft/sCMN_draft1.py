import numpy as np
from vispy import gloo
from scipy.ndimage import gaussian_filter
from vispy import app
import cv2 as cv

def load_shaderfile(fn):
    with open(fn, 'r') as shaderfile:
        return (shaderfile.read())


vert_update = """
#version 130
attribute vec3 a_positions;
void main (void) {
    gl_Position = vec4(a_positions, 1.0);
}
"""

frag_inspect="""
uniform vec2 u_resolution;
uniform sampler2D p_dotimg;
void main() {
    vec2 st = gl_FragCoord.xy / u_resolution.xy;
    gl_FragColor = vec4(0.,step(.6,texture2D(p_dotimg, st).r),0.4,1.);
}"""

frag_update = """
uniform vec2 u_resolution;
uniform sampler2D p_positions;
uniform sampler2D o_positions;
uniform sampler2D p_moments;
uniform sampler2D p_dotimg;
uniform float u_time;
varying vec2 v_index;
vec2 rand(vec2 st){
    return vec2(fract(sin(dot(st, vec2(12.9898, 78.233))) * 43758.5453),
                fract(cos(dot(st, vec2(12.9898, 78.233))) * 52958.1113));
}

void main() {
    vec2 st = gl_FragCoord.xy / u_resolution.xy;
    vec2 pos = texture2D(p_positions, st).xy;
    pos += (texture2D(p_moments,pos).xy-.5);
    pos = fract(pos);
    if(texture2D(p_dotimg, pos).r>.2){
        pos = texture2D(o_positions,rand(st+u_time)).xy;
    }
    gl_FragColor = vec4(pos,0.,1.);
}
"""

vert_draw = """
#version 120
// Uniforms
uniform sampler2D p_positions;
uniform sampler2D o_positions;
uniform float u_radius;
uniform vec2 u_resolution;
attribute vec2  a_index;
varying vec2 v_center;
varying vec2 v_index;

void main (void) {
    v_index = a_index;
    vec2 v_pos = texture2D(p_positions, a_index).xy;
    v_center = v_pos*u_resolution;
    gl_PointSize = 2.0 + ceil(2.0*u_radius);
    //if(v_pos.x<0){
    //    v_pos.x += 1;
    //}
    gl_Position =  vec4(2*v_pos-1, 0.0, 1.0);
}
"""

frag_draw = """
varying vec2 v_center;
uniform float u_alpha;
uniform float u_radius;
uniform vec2 u_resolution;
varying vec2 v_index;
uniform float bwratio;
float rand(vec2 st){
    return fract(sin(dot(st, vec2(12.9898, 78.233))) * 43758.5453);
}
void main()
{
    vec2 postmp = v_center;
    vec2 p = gl_FragCoord.xy - postmp;    
    float a = step(length(p),u_radius);
    gl_FragColor = vec4(vec3(step(.5,rand(v_index))), a*u_alpha);
}
"""
# TODO : CALCULATE DIVERGENCE POINT FOR RESETTING
# ------------------------------------------------------------ Canvas class ---
class Canvas(app.Canvas):
    fbo_render_pos = np.array([[-1.0, -1.0, 0.0], [-1.0, +1.0, 0.0],
                               [+1.0, -1.0, 0.0], [+1.0, +1.0, 0.0, ]], np.float32)
    fbo_tex_coord  = np.array([[0.0, 0.0], [0.0, 1.0],
                               [1.0, 0.0], [1.0, 1.0]], np.float32)
    def __init__(self):
        np.random.seed(77)
        app.Canvas.__init__(self, keys='interactive', size=(500, 500))

        # Create vertices
        n = 10000
        fbo_shape = (self.physical_size[1], self.physical_size[0],3)

        posarray = np.meshgrid(np.linspace(0, 1, self.physical_size[0]), np.linspace(0, 1, self.physical_size[1]))
        posarray = np.concatenate((np.asarray(posarray),posarray[0][np.newaxis,...]*0),axis=0)
        posarray = np.transpose(posarray,[1,2,0]).astype(np.float32)
        self.buf_pos = gloo.Texture2D(posarray)
        self.pos_fbo = gloo.FrameBuffer(color=self.buf_pos)
        self.buf_divmask = gloo.Texture2D(np.zeros(fbo_shape).astype(np.float32))
        self.divmask_fbo = gloo.FrameBuffer(color=self.buf_divmask)
        self.buf_img = gloo.Texture2D(np.zeros(fbo_shape).astype(np.float32))
        self.pntpos_fbo = gloo.FrameBuffer(color=self.buf_img)

        self.divmat_x = np.random.rand(40,40,20)-.5
        self.divmat_y = np.random.rand(40,40,20)-.5
        divmat_x = gaussian_filter(self.divmat_x.astype(np.float32),(5,5,10))
        divmat_y = gaussian_filter(self.divmat_y.astype(np.float32),(5,5,10))
        flowfield = np.concatenate((divmat_x[...,int(self.divmat_y.shape[-1]/2)][...,np.newaxis],
                                    divmat_y[...,int(self.divmat_y.shape[-1]/2)][...,np.newaxis],
                                    np.zeros(self.divmat_x[...,0].shape+(1,))),axis=2).astype(np.float32)+.5
        # divmask = np.concatenate((divmat[...,np.newaxis]*0,
        #                           divmat_norm[...,np.newaxis] > .0008,
        #                           divmat[...,np.newaxis]*0), axis=2).astype(np.float32)
        # divmask = divmask.astype(np.float32)
        # cv.imshow('im',divmask)
        # flowfield = cv.GaussianBlur(np.random.rand(*fbo_shape),(181,181),0)
        # flowfield = flowfield.astype(np.float32)+.5
        # flowfield_norm = np.sqrt(np.sum(flowfield[:,:,:2]**2,axis = 2))
        # ffdx = cv.Sobel(flowfield[:,:,0]/flowfield_norm,cv.CV_64F,1,0,ksize=25)
        # ffdy = cv.Sobel(flowfield[:,:,1]/flowfield_norm,cv.CV_64F,0,1,ksize=25)
        # ffdiv = (ffdx+ffdy)[...,np.newaxis]
        # divmask = np.concatenate((ffdiv>0.01,ffdiv<-0.01,ffdiv*0),axis=2). astype(np.float32)-.1
        self._program_inspect = gloo.Program(vert_update,frag_inspect)
        self._program_inspect["u_resolution"] = self.physical_size
        self._program_inspect['p_dotimg'] = self.buf_img
        self._program_inspect['a_positions'] = self.fbo_render_pos

        self._program_update = gloo.Program(vert_update,frag_update)
        self._program_update["u_resolution"] = self.physical_size
        self._program_update['p_dotimg'] = self.buf_img
        self._program_update['u_time'] = 0
        self._program_update['p_positions'] = self.buf_pos
        self._program_update['o_positions'] = posarray
        self._program_update['p_moments'] = flowfield
        self._program_update['a_positions'] = self.fbo_render_pos

        a_index = np.random.rand(n,2).astype(np.float32)
        self._program_draw = gloo.Program(vert_draw,frag_draw)
        self._program_draw['a_index'] = a_index
        self._program_draw['p_positions'] = self.buf_pos
        self._program_draw['o_positions'] = posarray
        self._program_draw["u_resolution"] = self.physical_size
        self._program_draw['u_radius'] = 2
        self._program_draw['u_alpha'] = 1
        self._program_draw['bwratio'] = .5
        gloo.set_state(blend=True, blend_func=('src_alpha', 'one_minus_src_alpha'), clear_color='white')
        self._timer = app.Timer(1/180, connect=self.update, start=True)
        self.show()

    def on_draw(self, event):
        # self.divmat_x = np.append(self.divmat_x,np.random.rand(*(self.divmat_x.shape[:-1]+(1,)))-.5,axis=-1)
        # self.divmat_x = np.delete(self.divmat_x,0,axis=-1)
        # self.divmat_y = np.append(self.divmat_y,np.random.rand(*(self.divmat_y.shape[:-1]+(1,)))-.5,axis=-1)
        # self.divmat_y = np.delete(self.divmat_y,0,axis=-1)
        # divmat_x = gaussian_filter(self.divmat_x.astype(np.float32),(4,4,10))
        # divmat_y = gaussian_filter(self.divmat_y.astype(np.float32),(4,4,10))
        # flowfield = np.concatenate((divmat_x[...,int(divmat_x.shape[-1]/2)][...,np.newaxis],
        #                             divmat_y[...,int(divmat_y.shape[-1]/2)][...,np.newaxis],
        #                             np.zeros(self.divmat_x[...,0].shape+(1,))),axis=2). astype(np.float32)+.5
        # self._program_update['p_moments'] = flowfield
        self.pntpos_fbo.activate()
        gloo.clear([0,0,0,1])
        self._program_draw['u_alpha'] = 1/10
        self._program_draw['u_radius'] = 4
        self._program_draw['bwratio'] = -1
        self._program_draw.draw('points')
        self.pntpos_fbo.deactivate()

        gloo.clear()
        self._program_update['u_time'] = np.sin(self._timer.elapsed)
        self.pos_fbo.activate()
        self._program_update.draw('triangle_strip')
        self.pos_fbo.deactivate()

        gloo.clear([0.5,0.5,0.5,1])
        self._program_draw['u_alpha'] = 1
        self._program_draw['u_radius'] = 2
        self._program_draw['bwratio'] = .5
        # self._program_inspect.draw('triangle_strip')
        self._program_draw.draw('points')

    def on_resize(self, event):
        width, height = self.physical_size
        gloo.set_viewport(0, 0, width, height)
        self._program_update["u_resolution"] = [width, height]
        self._program_draw["u_resolution"] = [width, height]



if __name__ == '__main__':
    c = Canvas()
    c.measure_fps()
    app.run()
