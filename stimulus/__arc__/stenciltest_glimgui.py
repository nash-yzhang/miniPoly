# -----------------------------------------------------------------------------
# Python and OpenGL for Scientific Visualization
# www.labri.fr/perso/nrougier/python+opengl
# Copyright (c) 2017, Nicolas P. Rougier
# Distributed under the 2-Clause BSD License.
# -----------------------------------------------------------------------------
from scipy import signal
from Glimgui.glarage import *
from glumpy import gl, glm, gloo
self = None
def prepare():
    self._clock.set_fps_limit(70)
    self.V, self.I, tileDist, tileCen, tileOri = icoSphere(2)  # Generate
    sp_sigma = .8  # spatial CR
    tp_sigma = 15  # temporal CR
    spkernel = np.exp(-(tileDist ** 2) / (2 * sp_sigma ** 2))
    spkernel *= spkernel > .001
    tp_min_length = np.int(np.ceil(np.sqrt(-2 * tp_sigma ** 2 * np.log(.01 * tp_sigma * np.sqrt(2 * np.pi)))))
    tpkernel = np.linspace(-tp_min_length, tp_min_length, num=2 * tp_min_length + 1)
    tpkernel = 1 / (tp_sigma * np.sqrt(2 * np.pi)) * np.exp(-(tpkernel) ** 2 / (2 * tp_sigma ** 2))
    tpkernel *= tpkernel > .001

    flowvec = np.random.normal(size=[np.int(self.I.size / 3), 200, 3])  # Random white noise motion vector
    flowvec /= vecNorm(flowvec)[:, :, None]
    tpsmooth_x = signal.convolve(flowvec[:, :, 0], tpkernel[np.newaxis, :], mode='same')
    tpsmooth_y = signal.convolve(flowvec[:, :, 1], tpkernel[np.newaxis, :], mode='same')
    tpsmooth_z = signal.convolve(flowvec[:, :, 2], tpkernel[np.newaxis, :], mode='same')
    spsmooth_x = np.dot(spkernel, tpsmooth_x)
    spsmooth_y = np.dot(spkernel, tpsmooth_y)
    spsmooth_z = np.dot(spkernel, tpsmooth_z)  #
    spsmooth_Q = qn.qn(np.array([spsmooth_x, spsmooth_y, spsmooth_z]).transpose([1, 2, 0]))

    tileCen_Q = qn.qn(tileCen)
    tileOri_Q1 = qn.qn(np.real(tileOri)).normalize[:, None]
    tileOri_Q2 = qn.qn(np.imag(tileOri)).normalize[:, None]
    projected_motmat = qn.projection(tileCen_Q[:, None], spsmooth_Q)
    self.motmatFull = qn.qdot(tileOri_Q1, projected_motmat) - 1.j * qn.qdot(tileOri_Q2, projected_motmat)


    def cart2sph(cx, cy, cz):
        cxy = cx + cy * 1.j
        azi = np.angle(cxy)
        elv = np.angle(np.abs(cxy) + cz * 1.j)
        return azi, elv


    spsmooth_azi = np.angle(spsmooth_x + spsmooth_y * 1.j) * 0 + 1
    spsmooth_elv = np.angle(np.abs(spsmooth_x + spsmooth_y * 1.j) + spsmooth_z * 1.j) * 0

    startpoint = cen2tri(np.random.rand(np.int(self.I.size / 3)), np.random.rand(np.int(self.I.size / 3)), .1)
    # V_azi, V_elv = cart2sph(*V['position'].T)

    self.V['texcoord'] = startpoint.reshape([-1, 2])
    self.V = self.V.view(gloo.VertexBuffer)
    self.I = self.I.view(gloo.IndexBuffer)
    self.t = 1

    sphV, sphI = UVsphere(np.pi / 2, np.pi, 20, 80)
    sphI = sphI[sphI.max(1) < len(sphV),:]
    mask_V = np.zeros(sphV.shape[0], [("position", np.float32, 3)])
    mask_V["position"] = sphV * np.mean(vecNorm(self.V['position']))

    self.mask_V = mask_V.view(gloo.VertexBuffer)
    self.mask_I = sphI.astype(np.uint32)
    self.mask_I = self.mask_I.view(gloo.IndexBuffer)

    model = np.eye(4, dtype=np.float32)
    rotateMat = glm.rotate(np.eye(4), 0, 0, 1, 0)
    translateMat = glm.translation(0, 0, -6)
    projectMat = glm.perspective(45.0, 1, 2.0, 100.0)

    shader_folder = './shaderfile/'
    vertex_shader_fn = 'VS_tex_1701.glsl'
    frag_shader_fn = 'FS_tex_1511.glsl'
    mask_vertex_fn = 'VS_mask_1701.glsl'
    mask_frag_fn = 'FS_ucolor_1311.glsl'

    vertex = load_shaderfile(shader_folder + vertex_shader_fn)
    fragment = load_shaderfile(shader_folder + frag_shader_fn)
    maskVertex = load_shaderfile(shader_folder + mask_vertex_fn)
    maskFrag = load_shaderfile(shader_folder + mask_frag_fn)

    self.patchMat = gloo.Program(vertex, fragment)
    self.patchMat.bind(self.V)
    self.patchMat['texture'] = np.uint8(np.random.randint(0, 2, [100, 100, 1]) * np.array([[[1, 1, 1]]]) * 255)
    self.patchMat['texture'].wrapping = gl.GL_REPEAT
    self.patchMat['u_rotmat'] = glm.rotate(np.eye(4), 0, 0, 0, 1) @ glm.rotate(np.eye(4), 90, 1, 0, 0)
    self.patchMat['u_transformation'] = translateMat @ projectMat
    self.patchMat['u_rotate'] = rotation2D(np.pi / 4)
    self.patchMat['u_shift'] = np.array([0.5, 0.5])
    self.patchMat['u_scale'] = .5 * np.array([1, 1])

    self.maskPatch = gloo.Program(maskVertex, maskFrag)
    self.maskPatch.bind(self.mask_V)
    self.maskPatch['u_rotmat'] = glm.rotate(np.eye(4), 90, 0, 0, 1) @ glm.rotate(np.eye(4), 90, 1, 0, 0)
    self.maskPatch['u_transformation'] = translateMat @ projectMat
    self.maskPatch['u_rotate'] = rotation2D(np.pi / 4)
    self.maskPatch['u_shift'] = np.array([0.5, 0.5])
    self.maskPatch['u_scale'] = .5 * np.array([1, 1])
    self.maskPatch['u_color'] = np.array([0, 0, 0, 1])


def on_draw(dt):
    self.clear()
    tidx = np.mod(self.t, 199)  # Loop every 500 frames
    motmat = np.repeat(self.motmatFull[:, tidx], 3, axis=0)  # updating the motion matrix

    self.V['texcoord'] += np.array(
        [np.real(motmat), np.imag(motmat)]).T / 80  # update texture coordinate based on the current motion matrix
    for i in np.arange(4):
        self.maskPatch['u_rotmat'].reshape([4, 4]) @ glm.rotate(np.eye(4), .5, 0, 1, 1)
        self.maskPatch['u_rotate'] = rotation2D(np.pi / 4 + np.pi / 2 * i)
        self.maskPatch['u_shift'] = np.array([np.real(1.j ** (.5 + i)), np.imag(1.j ** (.5 + i))]) * .7

        self.patchMat['u_rotmat'] =  glm.rotate(np.eye(4), 90 * i, 0, 0, 1) @ glm.rotate(np.eye(4), 90, 1, 0, 0)
        self.patchMat['u_rotate'] = rotation2D(np.pi / 4 + np.pi / 2 * i)
        self.patchMat['u_shift'] = np.array([np.real(1.j ** (.5 + i)), np.imag(1.j ** (.5 + i))]) * .7

        if not self._has_pop:
            gl.glEnable(gl.GL_DEPTH_TEST)
            self.patchMat.draw(gl.GL_TRIANGLES, self.I)
        else:
        # if True:
            gl.glEnable(gl.GL_STENCIL_TEST)
            gl.glStencilFunc(gl.GL_ALWAYS, 1, 1)
            gl.glStencilMask(0X01)
            gl.glClear(gl.GL_STENCIL_BUFFER_BIT)
            gl.glDisable(gl.GL_DEPTH_TEST)
            gl.glColorMask(gl.GL_FALSE, gl.GL_FALSE, gl.GL_FALSE, gl.GL_FALSE)
            self.maskPatch.draw(gl.GL_TRIANGLES, self.mask_I)

            gl.glEnable(gl.GL_DEPTH_TEST)
            gl.glStencilFunc(gl.GL_EQUAL, 0X01, 1)
            gl.glStencilOp(gl.GL_KEEP, gl.GL_KEEP, gl.GL_REPLACE)
            gl.glStencilMask(0)
            gl.glColorMask(gl.GL_TRUE, gl.GL_TRUE, gl.GL_TRUE, gl.GL_TRUE)
            self.patchMat.draw(gl.GL_TRIANGLES, self.I)

    self.t += 1

import imgui
def set_imgui_widgets():
    imgui.begin('FPS')
    imgui.text("Frame duration: %.2f ms" %(self.dt*1000))
    imgui.text("FPS: %d Hz"%round(1/(self.dt+1e-8)))
    imgui.end()
    if not self._has_pop:
        imgui.begin("Stencil test", True)
        ww, wh = imgui.get_window_size()
        winPos = imgui.get_cursor_screen_pos()
        pop_on_resize(ww,wh)
        self.clear()
        self._framebuffer.activate()
        self.dispatch_event("on_draw", .0)
        self._framebuffer.deactivate()
        draw_list = imgui.get_window_draw_list()
        draw_list.add_image(self._framebuffer.color[0]._handle, tuple(winPos), tuple([winPos[0] + ww, winPos[1] + wh]),
                            (0, 1), (1, 0))

        imgui.invisible_button("popup", max(ww - 30,1), max(wh - 50,1))
        if imgui.begin_popup_context_item("Item Context Menu", mouse_button=0):
            if imgui.selectable("Pop out")[1]:
                self.pop(ww, wh, winPos[0], winPos[1], title='FreqMapper')
            imgui.end_popup()
        imgui.end()
    else:
        pass
#
def pop_on_resize(width, height):
    # global ratio
    if width > height:
        ratio = np.array([height / width, 1])
    else:
        ratio = np.array([1, width / height])
    self.maskPatch['u_scale'] = .6 * ratio
    self.patchMat['u_scale'] = .6 * ratio
#
#
# def on_init():
#     gl.glEnable(gl.GL_DEPTH_TEST)
#
#
# app.run(framerate=60)
