import numpy as np
from importlib import util, reload
import sys, os

from vispy import gloo, app
import PyQt5.QtWidgets as qw

from bin.glsl_preset import glCanvas, renderer
from bin.minion import AbstractMinionMixin


class GLDisplay(glCanvas, AbstractMinionMixin):
    def __init__(self, handler, *args, controllerProcName=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._processHandler = handler
        self._setTime = 0
        self._tic = 0
        self._rmtShutdown = False
        if controllerProcName:
            self.controllerProcName = controllerProcName

    @property
    def controllerProcName(self):
        return self._controllerProcName

    @controllerProcName.setter
    def controllerProcName(self, value):
        self._controllerProcName = value

    def parse_msg(self, msg_type, msg):
        if msg_type == 'rendering_script':
            self.rendererScriptName = msg
            self.rendererName = self.rendererScriptName.split("/")[-1][:-3]
            self._processHandler.info(
                "Received rendering script [{}] from [{}]".format(self.rendererScriptName, self.controllerProcName))
            self.importModuleFromPath()
            self._renderer = self.imported.Renderer(self)
            self.load(self._renderer)
            self._processHandler.info("Running script [{}]".format(self.rendererScriptName))
        elif msg_type == 'rendering_shader':
            self._renderer.reload(msg)

    def on_timer(self, event):
        if self.timer.elapsed - self._setTime > .01:  # Limit the call frequency to 1 second

            # Check if any remote calls have been set first before further processing
            if self._processHandler.status == -1:
                self._rmtShutdown = True
                self.on_close()
            elif self._processHandler.status == 0:
                self.on_close()

            self._setTime = np.floor(self.timer.elapsed)
            self.get(self.controllerProcName)
            # msg,_ = self._processHandler.get(self.controllerProcName)
            # if msg is not None:
            #     if msg[0] == 'rendering_script':
            #         self.rendererScriptName = msg[1]
            #         self.rendererName = self.rendererScriptName.split("/")[-1][:-3]
            #         self._processHandler.info("Received rendering script [{}] from [{}]".format(self.rendererScriptName,self.controllerProcName))
            #         self.importModuleFromPath()
            #         self._renderer = self.imported.Renderer(self)
            #         self.load(self._renderer)
            #         self._processHandler.info("Running script [{}]".format(self.rendererScriptName))
            #     elif msg[0] == 'rendering_shader':
            #         self._renderer.reload(msg[1])
        self.update()

    def on_close(self):
        if not self._rmtShutdown:
            self._processHandler.set_state(self._processHandler.name, 'status', 0)
        self.close()

    def importModuleFromPath(self):
        spec = util.spec_from_file_location(self.rendererName, location=self.rendererScriptName)
        self.imported = util.module_from_spec(spec)
        sys.modules[self.rendererName] = self.imported
        spec.loader.exec_module(self.imported)


class customWidget(qw.QWidget):
    def __init__(self, mainW):
        super().__init__()
        self._mainWindow = mainW
        self._processHandler = self._mainWindow._processHandler
        self._layout = qw.QVBoxLayout()
        self.setLayout(self._layout)
        self.load_button = qw.QPushButton("Load Shader")
        self.load_button.setShortcut("Ctrl+Shift+O")
        self.load_button.clicked.connect(self.loadfile)
        self._layout.addWidget(self.load_button, 1)
        self._autoR_box = qw.QCheckBox("auto refresh")
        self._autoR_box.setChecked(False)
        self._autoR_box.clicked.connect(self.auto_refresh)
        self.refresh_button = qw.QPushButton("Refresh")
        self.refresh_button.setShortcut("Ctrl+Shift+R")
        self.refresh_button.clicked.connect(self.refresh)
        self._sublayout = qw.QHBoxLayout()
        self._sublayout.addWidget(self._autoR_box)
        self._sublayout.addWidget(self.refresh_button, 1)
        self._layout.addLayout(self._sublayout)

        spacer = qw.QSpacerItem(1, 1, qw.QSizePolicy.Minimum, qw.QSizePolicy.MinimumExpanding)
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
                                                     , qw.QFileDialog.DontUseNativeDialog)
        self.FSname = self.FSname[0]
        if self.FSname:
            self._fs = load_shaderfile(self.FSname)
            # self._processHandler.reload(self._fs)
            self._processHandler.send('Display', ('rendering_shader', self._fs))

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
            self._processHandler.send('Display', ('rendering_shader', self._fs))


class Renderer(renderer):

    def __init__(self, canvas):
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
        self.program = gloo.Program(self.VS, self.FS)
        self.bg = gloo.Program(self.VS, self.FS)

    def init_renderer(self):
        self.program['a_pos'] = np.array([[-1., -1.], [-1., 1.], [1., -1.], [1., 1.]], np.float32)  # /2.
        # self.bg['a_pos'] = np.array([[-1.,-1.],[-1.,1.],[1.,-1.],[1.,1.]],np.float32)
        self.program['u_time'] = 0
        self.program['u_alpha'] = np.float32(1)
        # self.bg['u_alpha'] = np.float32(.15)
        gloo.set_state("translucent")
        self.program['u_resolution'] = (self.canvas.size[0], self.canvas.size[1])

    def on_draw(self, event):
        gloo.clear('white')
        u_time = self.canvas.timer.elapsed
        self.program['u_time'] = u_time
        self.program.draw('triangle_strip')
        # self.program.draw('points')
        # self.bg.draw('triangle_strip')
