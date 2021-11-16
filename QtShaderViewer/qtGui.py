import PyQt5.QtCore as qc
import PyQt5.QtWidgets as qw
import glsl_preset as gp
import traceback,sys,os
from importlib import util, reload

class MainWindow(qw.QMainWindow):

    def __init__(self, windowSize = (400,600), rendererName = None):
        super().__init__()
        self.setWindowTitle("GLSL viewer")
        self.resize(*windowSize)
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
        self._vcanvas = None
        self.rendererName = ''
        self.rendererScriptName = ''
        self.central_widget = qw.QWidget()               # define central widget
        self.setCentralWidget(self.central_widget)
        self.boxlayout = qw.QVBoxLayout()
        self.central_widget.setLayout(self.boxlayout)
        self.canvasLabel = qw.QLabel("Load stimulus via File (Ctrl+O)")
        self.canvasLabel.setAlignment(qc.Qt.AlignCenter)
        self.boxlayout.addWidget(self.canvasLabel)
        self.customWidget = None
        if rendererName:
            self._load(rendererName)

    def _load(self,rendererScriptName):
        try:
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
                    self.customWidget = None
                if hasattr(self.imported,'customWidget'):
                    self.customWidget = self.imported.customWidget(self)
                    self.boxlayout.addWidget(self.customWidget)
        except Exception:
            print(traceback.format_exc())

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


app = qw.QApplication(sys.argv)
w = MainWindow(rendererName='planeRenderer.py')
w.show()
app.exec()