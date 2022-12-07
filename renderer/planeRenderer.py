from vispy import gloo
import os
import numpy as np
from bin.display import GLRenderer
import PyQt5.QtWidgets as qw
import PyQt5.QtCore as qc
from utils import load_shaderfile

class Widget(qw.QWidget):
    def __init__(self,mainW):
        super().__init__()
        self._mainWindow = mainW
        self._processHandler = mainW._processHandler
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

        spacer = qw.QSpacerItem(1,1,qw.QSizePolicy.Minimum, qw.QSizePolicy.MinimumExpanding)
        self.layout().addItem(spacer)

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
                                                     "frag shader (*.frag)", ""
                                                     ,qw.QFileDialog.DontUseNativeDialog)
        self.FSname = self.FSname[0]
        if self.FSname:
            self._fs = load_shaderfile(self.FSname)
            # self._mainWindow._renderer.reload(self._fs)
            self.rpc_reload()

    def rpc_reload(self):
        self._processHandler.send(self._mainWindow._displayProcName,
                                  ('rendering_shader', self._fs))

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
            # self._mainWindow._renderer.reload(self._fs)
            self.rpc_reload()


class Renderer(GLRenderer):
    def __init__(self,canvas):
        super().__init__(canvas)
        self.VS = """
            #version 130
            attribute vec2 a_pos;
            varying vec2 v_pos;
            void main () {
                v_pos = a_pos;
                gl_PointSize = 10.;
                gl_Position = vec4(a_pos, 0.0, 1.0);
            }
            """

        self.FS = """
            varying vec2 v_pos; 
            uniform float u_alpha; 
            uniform float u_time; 
            void main() {
                float marker = step(.5,distance(gl_PointCoord,vec2(.5)));
                float color = sin(v_pos.x*20.+u_time*30.)/2.-.15+marker;
                gl_FragColor = vec4(vec3(color), u_alpha);
            }
        """
        self.FS2 = """
            varying vec2 v_pos; 
            void main() {
             float color = min(step(abs(v_pos.x),.97),step(abs(v_pos.y),.965));
             gl_FragColor = vec4(vec3(color), .5); }
        """
        self.program = gloo.Program(self.VS,self.FS)
        self.bg = gloo.Program(self.VS,self.FS)

    def init_renderer(self):
        self.program['a_pos'] = np.array([[-1.,-1.],[-1.,1.],[1.,-1.],[1.,1.]],np.float32)#/2.
        # self.bg['a_pos'] = np.array([[-1.,-1.],[-1.,1.],[1.,-1.],[1.,1.]],np.float32)
        self.program['u_time'] = 0
        self.program['u_alpha'] = np.float32(1)
        # self.bg['u_alpha'] = np.float32(.15)
        gloo.set_state("translucent")
        self.program['u_resolution'] = (self.canvas.size[0],self.canvas.size[1])

    def on_draw(self,event):
        gloo.clear('white')
        u_time = self.canvas.timer.elapsed
        self.program['u_time'] = u_time
        self.program.draw('triangle_strip')
        # self.program.draw('points')
        # self.bg.draw('triangle_strip')
