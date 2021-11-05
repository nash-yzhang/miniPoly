from vispy import gloo
from vispy.util.transforms import translate, rotate, perspective
import os
from sphModel import *
from glsl_preset import renderer, _default_sphere_VS, _default_sphere_FS
import PyQt5.QtWidgets as qw
import PyQt5.QtCore as qc
from utils import load_shaderfile

import_func_name = ['setGUI','loadshader']
self = None

class customWidget(qw.QWidget):
    def __init__(self,mainW):
        super().__init__()
        self._mainWindow = mainW
        self._layout = qw.QVBoxLayout()
        self.setLayout(self._layout)
        self.load_button = qw.QPushButton("Load Shader")
        self.load_button.setShortcut("Ctrl+Shift+O")
        self.load_button.clicked.connect(self.loadfile)
        self._layout.addWidget(self.load_button,1)
        self._autoR_box = qw.QCheckBox("auto refresh")
        self._autoR_box.setChecked(False)
        self._autoR_box.clicked.connect(self.auto_refresh)
        self.refresh_button = qw.QPushButton("Refresh")
        self.refresh_button.setShortcut("Ctrl+Shift+R")
        self.refresh_button.clicked.connect(self.refresh)
        self._sublayout = qw.QHBoxLayout()
        self._sublayout.addWidget(self._autoR_box)
        self._sublayout.addWidget(self.refresh_button,1)
        self._layout.addLayout(self._sublayout)

        self._fs = None
        os.environ["QT_FILESYSTEMMODEL_WATCH_FILES"] = '1'
        self.FSname = None
        self.FSwatcher = qc.QFileSystemWatcher([])
        self.FSwatcher.fileChanged.connect(self.refresh)

    def loadfile(self):
        if self.FSname is not None:
            self.FSwatcher.removePath(self.FSname)
        self._autoR_box.setChecked(False)
        self.FSname = qw.QFileDialog.getOpenFileName(self, 'Open File', './shader',
                                                     "frag shader (*.*)", ""
                                                     ,qw.QFileDialog.DontUseNativeDialog)
        self.FSname = self.FSname[0]
        if self.FSname:
            self._fs = load_shaderfile(self.FSname)
            self._mainWindow._renderer.reload(self._fs)

    def auto_refresh(self, checked):
        if checked and self.FSname is not None:
            self.FSwatcher.addPath(self.FSname)
        elif not checked and self.FSname is not None:
            self.FSwatcher.removePath(self.FSname)
        else:
            self._autoR_box.setChecked(False)

    def refresh(self, checked):
        if self.FSname is not None:
            self._fs = load_shaderfile(self.FSname)
            self._mainWindow._renderer.reload(self._fs)


def loadshader():
    if self.FSname is not None:
        self.FSwatcher.removePath(self.FSname)
    self.FSname = qw.QFileDialog.getOpenFileName(self, 'Open File', './shader', "frag shader (*.glsl *.vert *.frag)", "", qw.QFileDialog.DontUseNativeDialog)

    self.FSname = self.FSname[0]
    self._autoR_box.setChecked(False)
    if self.FSname:
        self._fs = load_shaderfile(self.FSname)
        self._renderer.reload(self._fs)

class Renderer(renderer):

    def __init__(self,canvas):
        super().__init__(canvas)
        self.VS = _default_sphere_VS
        self.FS = _default_sphere_FS
        self.program = gloo.Program(self.VS,self.FS)


    def init_renderer(self):
        self._vertices,self._faces = uv_sphere(60,40)
        self.translate = -5
        self.view = translate((0, 0, self.translate))
        self.model = np.eye(4, dtype=np.float32)
        self.program['u_model'] = self.model
        self.program['u_view'] = self.view
        self.phi, self.theta = 0, 0
        self.program['a_pos'] = qn.qn(self._vertices)['xyz'].astype(np.float32)
        projection = perspective(45.0, self.canvas.size[0] / float(self.canvas.size[1]),
                                 2.0, 10.0)
        self.program['u_projection'] = projection
        self.sph_index = gloo.IndexBuffer(self._faces.astype(np.uint16))
        gloo.set_state(clear_color='k', depth_test=True,)
        self.canvas.on_mouse_motion = self.on_mouse_motion
        self.canvas.on_mouse_wheel = self.on_mouse_wheel
        self.canvas.events.mouse_press.connect((self.canvas, "on_mouse_motion"))
        self.canvas.events.mouse_release.connect((self.canvas, "on_mouse_motion"))
        self.canvas.events.mouse_move.connect((self.canvas, "on_mouse_motion"))

    def on_draw(self,event):
        gloo.clear([.5,.5,.5],depth=True)
        u_time = self.canvas.timer.elapsed
        self.program['u_time'] = u_time
        self.program.draw('triangles',self.sph_index)

    def on_resize(self, event):
        gloo.set_viewport(0, 0, *self.canvas.physical_size)
        projection = perspective(45.0, self.canvas.size[0] / float(self.canvas.size[1]),
                                 2.0, 10.0)
        self.program['u_projection'] = projection

    def on_mouse_motion(self, event):
        if event.is_dragging and len(event.trail()) > 1:
            delta = event.trail()
            delta = delta[-2, :] - delta[-1, :]
            self.phi += delta[0] / self.canvas.size[0] * np.pi * 100
            self.theta -= delta[1] / self.canvas.size[1] * np.pi * 50
            self.model = np.dot(rotate(self.phi, (0, -1, 0)),
                                rotate(self.theta, (1, 0, 0)))
            self.program['u_model'] = self.model

    def on_mouse_wheel(self, event):
        self.translate += event.delta[1] / 10
        self.view = translate((0, 0, self.translate))
        self.program['u_view'] = self.view
        self.canvas.update()
