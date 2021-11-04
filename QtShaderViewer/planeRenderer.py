from vispy import gloo
import glsl_preset as gp
import os
import numpy as np
from glsl_preset import renderer, _default_plane_VS, _default_plane_FS
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
        self.VS = _default_plane_VS
        self.FS = _default_plane_FS
        self.program = gloo.Program(self.VS,self.FS)

    def init_renderer(self):
        self.program['a_pos'] = np.array([[-1.,-1.],[-1.,1.],[1.,-1.],[1.,1.]],np.float32)
        self.program['u_time'] = 0
        gloo.set_state(clear_color='w')
        self.program['u_resolution'] = (self.canvas.size[0],self.canvas.size[1])

    def on_draw(self,event):
        gloo.clear()
        u_time = self.canvas.timer.elapsed
        self.program['u_time'] = u_time
        self.program.draw('triangle_strip')
