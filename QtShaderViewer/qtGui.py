import PyQt5.QtCore as qc
import PyQt5.QtWidgets as qw
import glsl_preset as gp
import sys,os
from importlib import util, reload
from utils import load_shaderfile

#%%
class vispyCanvas(qw.QWidget):
    """
    This "window" is a QWidget. If it has no parent, it
    will appear as a free-floating window as we want.
    """
    def __init__(self,FS=None):
        super().__init__()
        self._vcanvas = gp.sphereCanvas(FS)
        self.setLayout(qw.QVBoxLayout())
        self.layout().addWidget(self._vcanvas.native)
        self.setStyleSheet("background: transparent; border: transparent;")

    def closeEvent(self,event):
        self._vcanvas.timer.stop()
        self._vcanvas.close()
        event.accept()

class MainWindow_2(qw.QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("GLSL viewer")
        self.resize(400,600)
        self._menubar = self.menuBar()
        self._menu_file = self._menubar.addMenu('File')
        loadfile = qw.QAction("Load",self)
        loadfile.setShortcut("Ctrl+O")
        loadfile.setStatusTip("Load renderer script")
        loadfile.triggered.connect(self.loadfile)
        reload = qw.QAction("Reload",self)
        reload.setShortcut("Ctrl+R")
        reload.setStatusTip("Reload renderer")
        reload.triggered.connect(self.reload)
        self._menu_file.addAction(loadfile)
        self._menu_file.addAction(reload)
        self.rendererScriptName = ''
        self.rendererName = ''
        self._vcanvas = None
        self.central_widget = qw.QWidget()               # define central widget
        self.setCentralWidget(self.central_widget)
        self.boxlayout = qw.QVBoxLayout()
        self.central_widget.setLayout(self.boxlayout)
        self.canvasLabel = qw.QLabel("Load stimulus via File (Ctrl+O)")
        self.canvasLabel.setAlignment(qc.Qt.AlignCenter)
        self.boxlayout.addWidget(self.canvasLabel)
        self.customWidget = None
        self.rendererScriptName = None

    def _load(self,rendererScriptName):
        if rendererScriptName:
            if rendererScriptName == self.rendererScriptName:
                reload(self.imported)
            else:
                self.rendererScriptName = rendererScriptName
                self.rendererName = self.rendererScriptName.split("/")[-1][:-3]
                self.importModuleFromPath()
            if self._vcanvas is None:
                self._vcanvas = gp.glCanvas()
                self._renderer = self.imported.Renderer(self._vcanvas)
                self._vcanvas.load(self._renderer)
                self.boxlayout.removeWidget(self.canvasLabel)
            else:
                self._renderer = self.imported.Renderer(self._vcanvas)
                self._vcanvas.load(self._renderer)
                self.boxlayout.removeWidget(self._vcanvas.native)
            self.boxlayout.addWidget(self._vcanvas.native)
            if self.customWidget is not None:
                self.boxlayout.removeWidget(self.customWidget)
            self.customWidget = self.imported.customWidget(self)
            self.boxlayout.addWidget(self.customWidget)

    def loadfile(self):
        rendererScriptName = qw.QFileDialog.getOpenFileName(self,'Open File','./renderer',"GLSL rendering script (*.py)","",qw.QFileDialog.DontUseNativeDialog)
        rendererScriptName = rendererScriptName[0]
        self._load(rendererScriptName)

    def reload(self):
        self._load(self.rendererScriptName)

    def importModuleFromPath(self):
        spec = util.spec_from_file_location(self.rendererName, location=self.rendererScriptName)
        self.imported = util.module_from_spec(spec)
        sys.modules[self.rendererName] = self.imported
        spec.loader.exec_module(self.imported)

class MainWindow(qw.QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("GLSL viewer")
        self.resize(400,600)
        self._menubar = self.menuBar()
        self._menu_file = self._menubar.addMenu('File')
        self._custom_menu_file = self._menubar.addMenu('Custom')
        loadfile = qw.QAction("Load",self)
        loadfile.setShortcut("Ctrl+O")
        loadfile.setStatusTip("Load fragment shader file")
        loadfile.triggered.connect(self.loadfile)
        self._menu_file.addAction(loadfile)
        self.central_widget = qw.QWidget()               # define central widget
        self.setCentralWidget(self.central_widget)
        self.boxlayout = qw.QVBoxLayout()
        self._vcanvas = gp.glCanvas()
        self._renderer = gp.sphereRenderer(self._vcanvas)
        self._vcanvas.load(self._renderer)
        self.central_widget.setLayout(self.boxlayout)
        self._autoR_box = qw.QCheckBox("auto refresh")
        self._autoR_box.setChecked(False)
        self._autoR_box.clicked.connect(self.auto_refresh)
        self.refresh_button = qw.QPushButton("Refresh")
        self.refresh_button.setShortcut("Ctrl+R")
        self.refresh_button.clicked.connect(self.refresh)
        self._sphere_box = qw.QCheckBox("Sphere")
        self._sphere_box.setChecked(True)
        self._sphere_box.clicked.connect(self._use_sphere)
        self._plane_box = qw.QCheckBox("Plane")
        self._plane_box.clicked.connect(self._use_plane)
        self.boxlayout.addWidget(self._vcanvas.native)
        self.sublayout = qw.QHBoxLayout()
        self.sublayout.addWidget(self._autoR_box)
        self.sublayout.addWidget(self.refresh_button)
        self.sublayout.addWidget(self._sphere_box)
        self.sublayout.addWidget(self._plane_box)
        self.boxlayout.addLayout(self.sublayout)

        self._fs = None
        os.environ["QT_FILESYSTEMMODEL_WATCH_FILES"] = '1'
        self.FSname = None
        self.FSwatcher = qc.QFileSystemWatcher([])
        self.FSwatcher.fileChanged.connect(self.refresh)

    def loadfile(self):
        if self.FSname is not None:
            self.FSwatcher.removePath(self.FSname)
        self.FSname = qw.QFileDialog.getOpenFileName(self,'Open File','./shader',"frag shader (*.glsl *.vert *.frag)","",qw.QFileDialog.DontUseNativeDialog)
        self.FSname = self.FSname[0]
        self._autoR_box.setChecked(False)
        if self.FSname:
            self._fs = load_shaderfile(self.FSname)
            self._renderer.reload(self._fs)

    #TODO: implement the auto file update system
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
            self._renderer.reload(self._fs)

    def _use_sphere(self,checked):
        if self.FSname is not None:
            self.FSwatcher.removePath(self.FSname)
            self._autoR_box.setChecked(False)
        self._renderer = gp.sphereRenderer(self._vcanvas)
        self._vcanvas.load(self._renderer)
        self._sphere_box.setChecked(True)
        self._plane_box.setChecked(False)

    def _use_plane(self,checked):
        if self.FSname is not None:
            self.FSwatcher.removePath(self.FSname)
            self._autoR_box.setChecked(False)
        self._renderer = gp.planeRenderer(self._vcanvas)
        self._vcanvas.load(self._renderer)
        self._sphere_box.setChecked(False)
        self._plane_box.setChecked(True)

    def show_new_window(self, checked):
        if self.w is None:
            self.w = vispyCanvas(self._fs)
            self.w.show()
        else:
            if not self.w.isVisible():
                self.w = None
                self.w = vispyCanvas()
                self.w.show()
            else:
                self.w.close()
                self.w = None


app = qw.QApplication(sys.argv)
w = MainWindow_2()
w.show()
app.exec()