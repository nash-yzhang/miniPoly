import numpy as np
from scipy import signal
from scipy.ndimage import gaussian_filter
from glarage import *
from glumpy import app, gl, glm, gloo
import imgui

self = None
def prepare():
    shader_folder = './shaderfile/'
    vertex_shader_fn = 'VS_tex_1511.glsl'
    frag_shader_fn = 'FS_tex_1511.glsl'

    vertex = load_shaderfile(shader_folder + vertex_shader_fn)
    fragment = load_shaderfile(shader_folder + frag_shader_fn)
    sphV, sphI = cylinder(np.pi * 2.001, 10, 1, 50, 100)
    tile_cen, tile_ori = tile_param(sphV,sphI)
    self.t = 0
    self.V = np.zeros(sphV[sphI.flatten(),:].shape[0], [("position", np.float32, 3),
                                 ("texcoord", np.float32, 2)])
    self.inputV = sphV[sphI.flatten(),:]
    inputazi,inputelv = cart2sph(self.inputV[:,0],self.inputV[:,1],self.inputV[:,2])
    inputazi_ptest = inputazi.reshape(-1,3)
    def d_range(data,rangeaxis = 0):
        return np.max(data,axis = rangeaxis)-np.min(data,axis = rangeaxis)
    
    inputazi_ptest[(d_range(inputazi_ptest,rangeaxis = 1)[:,None]*np.ones([1,3])>np.pi) & (inputazi_ptest<0)] = np.pi*2 - inputazi_ptest[(d_range(inputazi_ptest,rangeaxis = 1)[:,None]*np.ones([1,3])>np.pi) & (inputazi_ptest<0)]
    self.V["position"] = vecNormalize(self.inputV)
    self.I = np.arange(sphV[sphI.flatten(),:].shape[0]).astype(np.uint32)
    # startpoint = cen2tri(np.random.rand(np.int(self.I.size / 3)), np.random.rand(np.int(self.I.size / 3)), .05)
    self.V["texcoord"] = np.hstack([inputazi[:,None],inputelv[:,None]])/1 #startpoint.reshape([-1,2])
    self.V = self.V.view(gloo.VertexBuffer)
    self.I = self.I.view(gloo.IndexBuffer)

    sp_sigma = np.pi*2  # spatial CR
    tp_sigma = 15  # temporal CR

    radscale = gaussian_filter(np.random.normal(size=[51,101, 500]),[sp_sigma,sp_sigma/4,tp_sigma]).reshape([-1,500]) # Random white noise motion vector
    self.spsmoothrs = radscale[sphI.flatten(),:]

    motionmat = qn.qn(np.array([0,0,1]))
    mot2d = proj_motmat(tile_ori,tile_cen,motionmat)/4
    mot2d *= 0
    mot2d -= 1.j*.05
    # mot2d *= 1.j**1.0
    self.Shape = gloo.Program(vertex, fragment)
    self.Shape.bind(self.V)
    rotateMat = np.eye(4)#glm.rotate(np.eye(4), 0, 0, 0, 0)
    translateMat = glm.translation(0, 0, -0)
    projectMat = glm.perspective(130.0,  1, 0.001, 1000.0)
    self.Shape['u_transformation'] = rotateMat @ translateMat @ projectMat
    self.Shape['u_rotate'] = rotation2D(np.pi / 2)
    self.Shape['u_shift'] = np.array([.5, .5]) * 0
    self.Shape['texture'] = np.uint8(np.random.randint(0, 2, [500, 50, 1]) * np.array([[[1, 1, 1]]]) * 255)
    self.Shape['texture'].wrapping = gl.GL_REPEAT


def on_draw(dt):
    def d_range(data, rangeaxis=0):
        return np.max(data, axis=rangeaxis) - np.min(data, axis=rangeaxis)
    self.t += 1
    tempV = vecNormalize(self.inputV)*(self.spsmoothrs[:,np.mod(self.t,499)][:,None]*np.array([1,1,0])*10+1)+ np.array([np.sin(self.t/20), np.cos(self.t/20),0])/5
    temp_azi, temp_elv = cart2sph(tempV[:, 0], tempV[:, 1], tempV[:, 2])
    temp_azi = temp_azi.reshape(-1, 3)
    temp_ptest = (d_range(temp_azi, rangeaxis=1)[:, None] * np.ones([1, 3]) > np.pi) & (temp_azi< 0) & (temp_azi > -np.pi)
    temp_azi[temp_ptest] += (np.pi * 2)
    temp_azi = temp_azi.flatten()
    self.Shape['u_scale'] = 1, 1
    self.V["texcoord"] = np.hstack ([temp_azi[:, None] * 40 / 2 / np.pi, temp_elv[:, None]]) / 10  - np.array([self.t,self.t])*10**-3*2

    self.clear()
    gl.glEnable(gl.GL_DEPTH_TEST)
    self.framebuffer.activate()
    self.clear((0.1,0.1,0.1,1))
    self.Shape.draw(gl.GL_TRIANGLES, self.I)
    self.framebuffer.deactivate()

def set_imgui_widgets():
    imgui.begin("New window", True)
    ww, wh = imgui.get_window_size()
    winPos = imgui.get_cursor_screen_pos()
    self.dispatch_event("on_draw", .0)
    draw_list = imgui.get_window_draw_list()
    draw_list.add_image(self.framebuffer.color[0]._handle, tuple(winPos), tuple([winPos[0] + ww, winPos[1] + wh]),
                        (0, 1), (1, 0))
    imgui.end()