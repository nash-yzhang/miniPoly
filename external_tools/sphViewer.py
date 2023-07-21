import sphModel as sp
import numpy as np
from vispy import gloo
from vispy.util.transforms import rotate, translate
from vispy.app.canvas import MouseEvent
from vispy import app

class UVsphereViewer(app.Canvas):
    def __init__(self, *args,**kwargs):
        app.Canvas.__init__(self,*args,**kwargs)

class shaderViewer(app.Canvas):

    def __init__(self, fragshader):
        app.Canvas.__init__(self, keys='interactive', size=(480, 480), vsync=True)
        shader_dir = 'shader//sphCMN//'
        self.FS = fragshader
        self.renderer = gloo.Program(sp.load_shaderfile(shader_dir + 'VS_cartex2sph.glsl'), self.FS)
        self.renderer['a_pos'] = [[-1, -1], [-1, +1], [+1, -1], [+1, +1]]
        gloo.set_state(blend=True, blend_func=('src_alpha', 'one_minus_src_alpha'), clear_color='white')
        self.timer = app.Timer(1 / 60, start=True)
        self.apply_zoom()
        self.show()

    def on_draw(self, event):
        gloo.clear()
        self.renderer.draw('triangle_strip')

    def on_resize(self, event):
        self.apply_zoom()

    def apply_zoom(self):
        gloo.set_viewport(0, 0, self.physical_size[0], self.physical_size[1])
        self.renderer['u_resolution'] = self.physical_size

class patchViewer(app.Canvas):
    def __init__(self, texture, tex_vert, tex_face):
        app.Canvas.__init__(self, keys='interactive', size=(480, 480), vsync=True)
        self.idx = 0
        shader_dir = 'shader//sphCMN//'
        shader_name = ('patch2D','patch3D')
        self.VS = {i: sp.load_shaderfile(shader_dir + 'VS_' + i + '.glsl') for i in shader_name}
        self.FS = {i: sp.load_shaderfile(shader_dir + 'FS_' + i + '.glsl') for i in shader_name}
        self.tex_ibo = gloo.IndexBuffer(tex_face.astype(np.uint32))
        if tex_vert.shape[1] == 2:
            self.tex_renderer = gloo.Program(self.VS['patch2D'], self.FS['patch2D'])
        elif tex_vert.shape[1] == 3:
            self.tex_renderer = gloo.Program(self.VS['patch3D'], self.FS['patch3D'])
            self._tex_model = np.eye(4, dtype=np.float32)
            self._tex_projection = np.eye(4, dtype=np.float32)
            self._tex_view = np.eye(4, dtype=np.float32)
            self.tex_renderer['u_model'] = self._tex_model
            self.tex_renderer['u_view'] = self._tex_projection
            self.tex_renderer['u_projection'] = self._tex_view
        self.tex_renderer['a_pos'] = (tex_vert).astype(np.float32)
        if texture.ndim == 3:
            self.tex_renderer['a_color'] = np.squeeze(texture[self.idx, :, :]).astype(np.float32)
        else:
            self.tex_renderer['a_color'] = texture.astype(np.float32)
        self._tex_translate = 0
        self._tex_theta = 0
        self._tex_phi = 0
        self.events.mouse_press.connect((self, "on_mouse_motion"))
        self.events.mouse_release.connect((self, "on_mouse_motion"))
        self.events.mouse_move.connect((self, "on_mouse_motion"))
        gloo.set_state(blend=True, blend_func=('src_alpha', 'one_minus_src_alpha'), clear_color='white')
        self.timer = app.Timer(1 / 60, start=True)
        self.show()

    def on_draw(self, event):
        gloo.clear()
        self.tex_renderer.draw('triangles', self.tex_ibo)

    def on_mouse_motion(self, event: MouseEvent):
        if event.is_dragging and len(event.trail()) > 1:
            delta = event.trail()
            delta_sign = np.sign((np.sqrt((delta[-1, :] ** 2).sum()) > np.sqrt((delta[-2, :] ** 2).sum())) - .5)
            delta = delta[-2, :] - delta[-1, :]
            self._tex_phi += delta[0] / self.size[0] * np.pi * 100
            self._tex_theta -= delta[1] / self.size[1] * np.pi * 50
            self._tex_model = np.dot(rotate(self._tex_theta, (0, 0, 1)),
                                     rotate(self._tex_phi, (0, 1, 0)))
            self.tex_renderer['u_model'] = self._tex_model
        self.update()

    def on_resize(self, event):
        self.apply_zoom()

    def apply_zoom(self):
        gloo.set_viewport(0, 0, self.physical_size[0], self.physical_size[1])

    def on_mouse_wheel(self, event):
        self._tex_translate += event.delta[1] / 10
        self._tex_view = translate((0, 0, -self._tex_translate,))
        self.tex_renderer['u_view'] = self._tex_view
        self.update()

    def on_draw(self, event):
        gloo.set_state(depth_test=True)
        gloo.clear()
        self.tex_renderer.draw('triangles', self.tex_ibo)

class sphViewer(patchViewer):
    def __init__(self, sph_texture: tuple):
        self.sph_val, self.sph_vert, self.sph_face = sph_texture
        self.sph_vert = self.sph_vert/np.pi*[1,2]
        super().__init__(self.sph_val, self.sph_vert, self.sph_face)
        self.sph_ibo = self.tex_ibo
        shader_dir = 'shader//sphCMN//'
        shader_name = ('cartex2sph',)
        self.VS.update({i: sp.load_shaderfile(shader_dir + 'VS_' + i + '.glsl') for i in shader_name})
        self.FS.update({i: sp.load_shaderfile(shader_dir + 'FS_' + i + '.glsl') for i in shader_name})
        self.sph_texture = gloo.Texture2D(self.size[::-1] + (3,))
        self.sph_fbo = gloo.FrameBuffer(color=self.sph_texture,
                                        depth=gloo.RenderBuffer(self.physical_size[2::-1]))

        self.model = np.eye(4, dtype=np.float32)
        self.projection = np.eye(4, dtype=np.float32)
        self.view = np.eye(4, dtype=np.float32)
        self.phi, self.theta = (0., 0.)
        self.translate = 0

        self.drawer = gloo.Program(self.VS['cartex2sph'], self.FS['cartex2sph'])
        self.drawer['a_pos'] = [[-1, -1], [-1, +1], [+1, -1], [+1, +1]]
        self.drawer['u_texture'] = self.sph_texture
        self.drawer['u_model'] = self.model
        self.drawer['u_view'] = self.view
        self.drawer['u_projection'] = self.projection
        self.drawer['u_resolution'] = self.physical_size

        gloo.set_state(blend=True, blend_func=('src_alpha', 'one_minus_src_alpha'), clear_color='white')
        self.timer = app.Timer(1 / 60, connect=self.on_timer, start=True)
        self.events.mouse_press.connect((self, "on_mouse_motion"))
        self.events.mouse_release.connect((self, "on_mouse_motion"))
        self.events.mouse_move.connect((self, "on_mouse_motion"))
        self.apply_zoom()
        self.show()

    def on_timer(self, event):
        if self.sph_val.ndim == 3:
            self.idx += 1
            # self.idx = self.idx % self.sph_val.shape[0]
            # self.tex_renderer['a_color'] = np.squeeze(self.sph_val[self.idx, :, :]).astype(np.float32)
        # self.update()

    def on_mouse_motion(self, event: MouseEvent):
        if event.is_dragging and len(event.trail()) > 1:
            delta = event.trail()
            delta_sign = np.sign((np.sqrt((delta[-1, :] ** 2).sum()) > np.sqrt((delta[-2, :] ** 2).sum())) - .5)
            delta = delta[-2, :] - delta[-1, :]
            self.theta += delta[0] / self.size[0] * np.pi * 100
            self.phi -= delta[1] / self.size[1] * np.pi * 50
            self.model = np.dot(rotate(self.theta, (0, 0, 1)),
                                rotate(self.phi, (0, 1, 0)))
            self.drawer['u_model'] = self.model

        self.update()

    def on_mouse_wheel(self, event):
        self.translate += event.delta[1] / 100
        self.view = translate((0, 0, -self.translate,))
        self.drawer['u_view'] = self.view
        self.update()

    def on_resize(self, event):
        self.apply_zoom()

    def apply_zoom(self):
        gloo.set_viewport(0, 0, self.physical_size[0], self.physical_size[1])
        self.drawer['u_resolution'] = self.physical_size

    def on_draw(self, event):
        self.sph_fbo.activate()
        gloo.clear()
        self.tex_renderer.draw('triangles', self.sph_ibo)
        self.sph_fbo.deactivate()
        gloo.clear()
        self.drawer.draw('triangle_strip')

class MotionViewer(app.Application):
    # TODO: fix canvas context error
    def __init__(self,window_size,*args,**kwargs):
        super().__init__(backend_name='pyqt5')
        self.win_size = window_size
        self.timer = app.Timer(1 / 60,  start=True)
        self.prepare(*args,**kwargs)
        self._computer = MotionComputer(self,window_size)
        self._drawer = MotionDrawer(self,window_size,shared=self._computer)

    def prepare(self,motion_texture: tuple, n_motcue=10000, pntsize=3, collision_size=4):
        self.pntsize = pntsize
        self.n_motcue = n_motcue
        self.motCueIdx = np.random.rand(self.n_motcue, 2).astype(np.float32)
        self.idx = 0
        self.motion_val, self.motion_vert, self.motion_face = motion_texture
        self.position_map = np.random.randn(*(self.win_size[::-1] + (3,)))
        self.position_map /= 2 * np.sqrt((self.position_map ** 2).sum(axis=-1))[
            ..., np.newaxis]  # normalized to unit vector on sphere
        self.position_map += .5
        self.position_map = self.position_map.astype(np.float32)
        self.motion_texture = gloo.Texture2D(self.win_size[::-1] + (3,))
        self.position_texture = gloo.Texture2D(self.position_map)
        self.density_texture = gloo.Texture2D(self.win_size[::-1] + (3,))
        self.streamline_texture = gloo.Texture2D(self.win_size[::-1] + (4,))

        shader_dir = 'shader//sphCMN//'
        shader_name = ('density', 'uv_draw', 'draw', 'line', 'patch2D', 'updatePos', 'streamline')
        self.VS = {i: sp.load_shaderfile(shader_dir + 'VS_' + i + '.glsl') for i in shader_name}
        self.FS = {i: sp.load_shaderfile(shader_dir + 'FS_' + i + '.glsl') for i in shader_name}

        self.motmat_renderer = gloo.Program(self.VS['patch2D'], self.FS['patch2D'])
        self.motion_fbo = gloo.FrameBuffer(color=self.motion_texture,
                                           depth=gloo.RenderBuffer(self.win_size[2::-1]))
        self.motion_ibo = gloo.IndexBuffer(self.motion_face.astype(np.uint32))
        self.motmat_renderer['a_pos'] = (self.motion_vert / np.pi * [1, 2]).astype(np.float32)
        if self.motion_val.ndim == 3:
            self.motmat_renderer['a_color'] = np.squeeze(self.motion_val[self.idx, :, :]).astype(np.float32)
        else:
            self.motmat_renderer['a_color'] = self.motion_val.astype(np.float32)

        self.posmat_updater = gloo.Program(self.VS['updatePos'], self.FS['updatePos'])
        self.position_fbo = gloo.FrameBuffer(color=self.position_texture,
                                             depth=gloo.RenderBuffer(self.win_size[2::-1]))
        self.posmat_updater['a_pos'] = [[-1, -1], [-1, +1], [+1, -1], [+1, +1]]
        self.posmat_updater["u_resolution"] = self.win_size
        self.posmat_updater['C_posmat'] = self.position_map
        self.posmat_updater['a_motmat'] = self.motion_texture
        self.posmat_updater['a_posmat'] = self.position_texture
        self.posmat_updater['a_denmat'] = self.density_texture

        self.density_computer = gloo.Program(self.VS['density'], self.FS['density'])
        self.density_fbo = gloo.FrameBuffer(color=self.density_texture,
                                            depth=gloo.RenderBuffer(self.win_size[2::-1]))
        self.density_computer['a_pntidx'] = self.motCueIdx
        self.density_computer['a_posmat'] = self.position_texture
        self.density_computer["u_resolution"] = self.win_size
        self.density_computer['u_radius'] = collision_size / 180 * np.pi

        self.model = np.eye(4, dtype=np.float32)
        self.projection = np.eye(4, dtype=np.float32)
        self.view = np.eye(4, dtype=np.float32)
        self.phi, self.theta = (0., 0.)
        self.translate = 0

        self.drawer = gloo.Program(self.VS['draw'], self.FS['draw'])
        self.drawer['u_radius'] = pntsize
        self.drawer['a_pntidx'] = self.motCueIdx
        self.drawer['a_posmat'] = self.position_texture
        self.drawer['a_motmat'] = self.motion_texture
        self.drawer["u_resolution"] = self.win_size
        self.drawer['u_model'] = self.model
        self.drawer['u_view'] = self.view
        self.drawer['u_projection'] = self.projection

        self.uv_drawer = gloo.Program(self.VS['uv_draw'], self.FS['uv_draw'])
        self.uv_drawer['u_radius'] = pntsize
        self.uv_drawer['a_pntidx'] = self.motCueIdx
        self.uv_drawer['a_posmat'] = self.position_texture
        self.uv_drawer['a_motmat'] = self.motion_texture
        self.uv_drawer["u_resolution"] = self.win_size
        self.uv_drawer['u_model'] = self.model
        self.uv_drawer['u_view'] = self.view
        self.uv_drawer['u_projection'] = self.projection

        self.streamline_fbo = gloo.FrameBuffer(color=self.streamline_texture,
                                               depth=gloo.RenderBuffer(self.win_size[2::-1]))
        self.streamline_renderer = gloo.Program(self.VS['streamline'], self.FS['streamline'])
        self.streamline_renderer['a_pos'] = [[-1, -1], [-1, +1], [+1, -1], [+1, +1]]
        self.streamline_renderer['a_texcoord'] = [[0., 0.], [0., 1.], [1., 0.], [1., 1.]]
        self.streamline_renderer['buffer_tex'] = self.streamline_texture
        self.streamline_renderer['u_alpha'] = 1.

        self.motmat_changing = False
        self.streamline_mode = False
        self.uv_mode = False

class MotionCanvas(app.Canvas):

    def __init__(self, viewer:MotionViewer, window_size, **kwargs):
        app.Canvas.__init__(self, app=viewer, size=window_size, **kwargs)
        gloo.set_state(blend=True, blend_func=('src_alpha', 'one_minus_src_alpha'))
        self.viewer = viewer
        self.timer = self.viewer.timer
        self.timer.connect(self.on_timer)
        self.apply_zoom()

    def on_resize(self, event):
        self.apply_zoom()

    def apply_zoom(self):
        gloo.set_viewport(0, 0, self.physical_size[0], self.physical_size[1])

    def on_timer(self,event):
        self.update()

class MotionComputer(MotionCanvas):

    def __init__(self, viewer:MotionViewer, window_size):
        super().__init__(viewer, window_size, show=True, vsync=True, decorate=False)
        self.size = (1,1)
        self.position=(-1,-1)

    def apply_zoom(self):
        pass

    def on_draw(self,event):
        self.viewer.motion_fbo.activate()
        gloo.clear()
        self.viewer.motmat_renderer.draw('triangles', self.viewer.motion_ibo)
        self.viewer.motion_fbo.deactivate()

        gloo.clear()
        self.viewer.position_fbo.activate()
        self.viewer.posmat_updater.draw('triangle_strip')
        self.viewer.position_fbo.deactivate()

        self.viewer.density_fbo.activate()
        gloo.clear('black')
        self.viewer.density_computer.draw('points')
        self.viewer.density_fbo.deactivate()

    def on_timer(self, event):
        if self.viewer.motion_val.ndim == 3:
            if self.viewer.motmat_changing:
                self.viewer.idx += 1
                self.viewer.idx = self.viewer.idx % self.viewer.motion_val.shape[0]
                self.viewer.motmat_renderer['a_color'] = np.squeeze(self.viewer.motion_val[self.viewer.idx, :, :]).astype(np.float32)
        self.viewer.posmat_updater['u_time'] = self.timer.elapsed
        self.update()

class MotionDrawer(MotionCanvas):

    def __init__(self, viewer:MotionViewer, window_size, **kwargs):
        super().__init__(viewer, window_size, keys='interactive', show=True, vsync=True, **kwargs)
        self.events.mouse_press.connect((self, "on_mouse_motion"))
        self.events.mouse_release.connect((self, "on_mouse_motion"))
        self.events.mouse_move.connect((self, "on_mouse_motion"))

    def on_key_press(self, event):
        if event.text == ' ':
            if self.viewer.motmat_changing:
                self.viewer.motmat_changing = False
            else:
                self.viewer.motmat_changing = True

        if event.text == 's':
            if self.viewer.streamline_mode:
                self.viewer.streamline_fbo.activate()
                gloo.clear()
                self.viewer.streamline_fbo.deactivate()
                self.viewer.streamline_mode = False
            else:
                self.viewer.streamline_mode = True

        if event.text == 'c':
            if self.viewer.uv_mode:
                self.viewer.uv_mode = False
            else:
                self.viewer.uv_mode = True

    def on_mouse_motion(self, event: MouseEvent):
        if event.is_dragging and len(event.trail()) > 1:
            delta = event.trail()
            delta_sign = np.sign((np.sqrt((delta[-1, :] ** 2).sum()) > np.sqrt((delta[-2, :] ** 2).sum())) - .5)
            delta = delta[-2, :] - delta[-1, :]
            self.viewer.phi += delta[0] / self.size[0] * np.pi * 100
            self.viewer.theta -= delta[1] / self.size[1] * np.pi * 50
            self.viewer.model = np.dot(rotate(self.viewer.theta, (0, 0, 1)),
                                rotate(self.viewer.phi, (0, 1, 0)))
            self.viewer.drawer['u_model'] = self.viewer.model
            self.viewer.model = np.dot(rotate(self.viewer.theta, (0, 1, 0)),
                                rotate(self.viewer.phi, (0, 0, 1)))
            self.viewer.uv_drawer['u_model'] = self.viewer.model

        self.update()

    def on_mouse_wheel(self, event):
        self.viewer.translate += event.delta[1] / 100
        self.viewer.view = translate((0, 0, -self.viewer.translate,))
        self.viewer.drawer['u_view'] = self.viewer.view
        self.update()

    def on_draw(self, event):
        if not self.viewer.streamline_mode:
            gloo.clear('black')
            if self.viewer.uv_mode:
                self.viewer.uv_drawer.draw('points')
            else:
                self.viewer.drawer.draw('points')
        else:
            self.viewer.streamline_renderer['u_alpha'] = .5
            self.viewer.streamline_fbo.activate()
            self.viewer.streamline_renderer.draw('triangle_strip')
            if self.viewer.uv_mode:
                self.viewer.uv_drawer.draw('points')
            else:
                self.viewer.drawer.draw('points')
            self.viewer.streamline_fbo.deactivate()
            gloo.clear('black')
            self.viewer.streamline_renderer['u_alpha'] = 1.
            self.viewer.streamline_renderer.draw('triangle_strip')

    def apply_zoom(self):
        if np.min(self.physical_size)>0:
            gloo.set_viewport(0, 0, self.physical_size[0], self.physical_size[1])
            if hasattr(self,'viewer'):
                self.viewer.drawer['u_resolution'] = self.physical_size
            self.update()

class BasicMotion(app.Canvas):

    def __init__(self, motion_texture: tuple, n_motcue=10000, pntsize=3, collision_size=3):
        app.Canvas.__init__(self, keys='interactive', size=(480, 480), vsync=True)
        self.pntsize = pntsize
        self.n_motcue = n_motcue
        self.motCueIdx = np.random.rand(self.n_motcue, 2).astype(np.float32)
        self.idx = 0
        self.motion_val, self.motion_vert, self.motion_face = motion_texture
        self.position_map = np.random.randn(*(self.size[::-1] + (3,)))
        self.position_map /= 2 * np.sqrt((self.position_map ** 2).sum(axis=-1))[
            ..., np.newaxis]  # normalized to unit vector on sphere
        self.position_map += .5
        self.position_map = self.position_map.astype(np.float32)
        self.motion_texture = gloo.Texture2D(self.size[::-1] + (3,))
        self.position_texture = gloo.Texture2D(self.position_map)
        self.density_texture = gloo.Texture2D(self.size[::-1] + (3,))
        self.streamline_texture = gloo.Texture2D(self.size[::-1] + (4,))

        shader_dir = 'shader//sphCMN//'
        shader_name = ('density', 'uv_draw', 'draw', 'line', 'patch2D', 'updatePos', 'streamline')
        self.VS = {i: sp.load_shaderfile(shader_dir + 'VS_' + i + '.glsl') for i in shader_name}
        self.FS = {i: sp.load_shaderfile(shader_dir + 'FS_' + i + '.glsl') for i in shader_name}

        self.motmat_renderer = gloo.Program(self.VS['patch2D'], self.FS['patch2D'])
        self.motion_fbo = gloo.FrameBuffer(color=self.motion_texture,
                                           depth=gloo.RenderBuffer(self.physical_size[2::-1]))
        self.motion_ibo = gloo.IndexBuffer(self.motion_face.astype(np.uint32))
        self.motmat_renderer['a_pos'] = (self.motion_vert / np.pi * [1, 2]).astype(np.float32)
        if self.motion_val.ndim == 3:
            self.motmat_renderer['a_color'] = np.squeeze(self.motion_val[self.idx, :, :]).astype(np.float32)
        else:
            self.motmat_renderer['a_color'] = self.motion_val.astype(np.float32)

        self.posmat_updater = gloo.Program(self.VS['updatePos'], self.FS['updatePos'])
        self.position_fbo = gloo.FrameBuffer(color=self.position_texture,
                                             depth=gloo.RenderBuffer(self.physical_size[2::-1]))
        self.posmat_updater['a_pos'] = [[-1, -1], [-1, +1], [+1, -1], [+1, +1]]
        self.posmat_updater["u_resolution"] = self.physical_size
        self.posmat_updater['C_posmat'] = self.position_map
        self.posmat_updater['a_motmat'] = self.motion_texture
        self.posmat_updater['a_posmat'] = self.position_texture
        self.posmat_updater['a_denmat'] = self.density_texture

        self.density_computer = gloo.Program(self.VS['density'], self.FS['density'])
        self.density_fbo = gloo.FrameBuffer(color=self.density_texture,
                                            depth=gloo.RenderBuffer(self.physical_size[2::-1]))
        self.density_computer['a_pntidx'] = self.motCueIdx
        self.density_computer['a_posmat'] = self.position_texture
        self.density_computer["u_resolution"] = self.physical_size
        self.density_computer['u_radius'] = collision_size / 180 * np.pi

        self.model = np.eye(4, dtype=np.float32)
        self.projection = np.eye(4, dtype=np.float32)
        self.view = np.eye(4, dtype=np.float32)
        self.phi, self.theta = (0., 0.)
        self.translate = 0

        self.drawer = gloo.Program(self.VS['draw'], self.FS['draw'])
        self.drawer['u_radius'] = pntsize
        self.drawer['a_pntidx'] = self.motCueIdx
        self.drawer['a_posmat'] = self.position_texture
        self.drawer['a_motmat'] = self.motion_texture
        self.drawer["u_resolution"] = self.physical_size
        self.drawer['u_model'] = self.model
        self.drawer['u_view'] = self.view
        self.drawer['u_projection'] = self.projection

        self.uv_drawer = gloo.Program(self.VS['uv_draw'], self.FS['uv_draw'])
        self.uv_drawer['u_radius'] = pntsize
        self.uv_drawer['a_pntidx'] = self.motCueIdx
        self.uv_drawer['a_posmat'] = self.position_texture
        self.uv_drawer['a_motmat'] = self.motion_texture
        self.uv_drawer["u_resolution"] = self.physical_size
        self.uv_drawer['u_model'] = self.model
        self.uv_drawer['u_view'] = self.view
        self.uv_drawer['u_projection'] = self.projection

        self.streamline_fbo = gloo.FrameBuffer(color=self.streamline_texture,
                                               depth=gloo.RenderBuffer(self.physical_size[2::-1]))
        self.streamline_renderer = gloo.Program(self.VS['streamline'], self.FS['streamline'])
        self.streamline_renderer['a_pos'] = [[-1, -1], [-1, +1], [+1, -1], [+1, +1]]
        self.streamline_renderer['a_texcoord'] = [[0., 0.], [0., 1.], [1., 0.], [1., 1.]]
        self.streamline_renderer['buffer_tex'] = self.streamline_texture
        self.streamline_renderer['u_alpha'] = 1.

        self.motmat_changing = False
        self.streamline_mode = False
        self.uv_mode = False

        gloo.set_state(blend=True, blend_func=('src_alpha', 'one_minus_src_alpha'), clear_color='white')

        self.timer = app.Timer(1 / 120, connect=self.on_timer, start=True)
        self.events.mouse_press.connect((self, "on_mouse_motion"))
        self.events.mouse_release.connect((self, "on_mouse_motion"))
        self.events.mouse_move.connect((self, "on_mouse_motion"))
        self.apply_zoom()
        self.show()

    def on_key_press(self, event):
        if event.text == ' ':
            if self.motmat_changing:
                self.motmat_changing = False
            else:
                self.motmat_changing = True

        if event.text == 's':
            if self.streamline_mode:
                self.streamline_fbo.activate()
                gloo.clear()
                self.streamline_fbo.deactivate()
                self.streamline_mode = False
            else:
                self.streamline_mode = True

        if event.text == 'c':
            if self.uv_mode:
                self.uv_mode = False
            else:
                self.uv_mode = True

    def on_timer(self, event):
        if self.motion_val.ndim == 3:
            if self.motmat_changing:
                self.idx += 1
                self.idx = self.idx % self.motion_val.shape[0]
                self.motmat_renderer['a_color'] = np.squeeze(self.motion_val[self.idx, :, :]).astype(np.float32)
        self.posmat_updater['u_time'] = self.timer.elapsed
        self.update()

    def on_resize(self, event):
        self.apply_zoom()

    def on_mouse_motion(self, event: MouseEvent):
        if event.is_dragging and len(event.trail()) > 1:
            delta = event.trail()
            delta_sign = np.sign((np.sqrt((delta[-1, :] ** 2).sum()) > np.sqrt((delta[-2, :] ** 2).sum())) - .5)
            delta = delta[-2, :] - delta[-1, :]
            self.phi += delta[0] / self.size[0] * np.pi * 100
            self.theta -= delta[1] / self.size[1] * np.pi * 50
            self.model = np.dot(rotate(self.theta, (0, 0, 1)),
                                rotate(self.phi, (0, 1, 0)))
            self.drawer['u_model'] = self.model
            self.model = np.dot(rotate(self.theta, (0, 1, 0)),
                                rotate(self.phi, (0, 0, 1)))
            self.uv_drawer['u_model'] = self.model

        self.update()

    def on_mouse_wheel(self, event):
        self.translate += event.delta[1] / 100
        # self.translate = max(1, self.translate)
        self.view = translate((0, 0, -self.translate,))
        self.drawer['u_view'] = self.view
        self.update()

    def on_draw(self, event):

        self.motion_fbo.activate()
        gloo.clear()
        self.motmat_renderer.draw('triangles', self.motion_ibo)
        self.motion_fbo.deactivate()

        gloo.clear()
        self.position_fbo.activate()
        self.posmat_updater.draw('triangle_strip')
        self.position_fbo.deactivate()

        self.density_fbo.activate()
        gloo.clear('black')
        self.density_computer.draw('points')
        self.density_fbo.deactivate()

        if not self.streamline_mode:
            gloo.clear('black')
            if self.uv_mode:
                self.uv_drawer.draw('points')
            else:
                self.drawer.draw('points')
        else:
            self.streamline_renderer['u_alpha'] = .5
            self.streamline_fbo.activate()
            self.streamline_renderer.draw('triangle_strip')
            if self.uv_mode:
                self.uv_drawer.draw('points')
            else:
                self.drawer.draw('points')
            self.streamline_fbo.deactivate()
            gloo.clear('black')
            self.streamline_renderer['u_alpha'] = 1.
            self.streamline_renderer.draw('triangle_strip')

    def apply_zoom(self):
        gloo.set_viewport(0, 0, self.physical_size[0], self.physical_size[1])
        self.drawer['u_resolution'] = self.physical_size
