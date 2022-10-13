import PyQt5.QtWidgets as qw
import PyQt5.QtCore as qc
import traceback,sys
from importlib import util, reload

class GUICtrl(qw.QMainWindow):
    def __init__(self, processHandler, displayProcName = "Display", windowSize = (400,400), rendererName = None):
        super().__init__()
        self._processHandler = processHandler
        self._displayProcName = displayProcName
        self.setWindowTitle("GLSL Controller")
        self.resize(*windowSize)
        self._menubar = self.menuBar()
        self._menu_file = self._menubar.addMenu('File')
        self._menu_display = self._menubar.addMenu('Display')
        loadfile = qw.QAction("Load",self)
        loadfile.setShortcut("Ctrl+O")
        loadfile.setStatusTip("Load renderer script")
        loadfile.triggered.connect(self.loadfile)
        reload = qw.QAction("Reload",self)
        reload.setShortcut("Ctrl+R")
        reload.setStatusTip("Reload renderer")
        reload.triggered.connect(self.reload)
        Exit = qw.QAction("Quit",self)
        Exit.setShortcut("Ctrl+Q")
        Exit.setStatusTip("Exit program")
        Exit.triggered.connect(self.close)
        restartDisplay = qw.QAction("Restart Display",self)
        restartDisplay.setShortcut("Ctrl+Shift+R")
        restartDisplay.setStatusTip("Restart display process")
        restartDisplay.triggered.connect(self.restartDisplay)
        haltDisplay = qw.QAction("Suspend Display",self)
        haltDisplay.setShortcut("Ctrl+Shift+H")
        haltDisplay.setStatusTip("Suspend display process")
        haltDisplay.triggered.connect(self.suspendDisplay)
        self._menu_file.addAction(loadfile)
        self._menu_file.addAction(Exit)
        self._menu_display.addAction(restartDisplay)
        self._menu_display.addAction(haltDisplay)
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
                    self.importModuleFromPath()
                    self._processHandler.info("Reloaded rendering script {}".format(rendererScriptName))
                else:
                    self.rendererScriptName = rendererScriptName
                    self.rendererName = self.rendererScriptName.split("/")[-1][:-3]
                    self.importModuleFromPath()
                    self._processHandler.info("Loaded rendering script: {}".format(rendererScriptName))
                self._processHandler.info("Forwarding script [{}] to [{}]".format(rendererScriptName,self._displayProcName))
                self._processHandler.send(self._displayProcName,('rendering_script',rendererScriptName))
                # Load GUI
                if self.customWidget is not None:
                    self.boxlayout.removeWidget(self.customWidget)
                    self.customWidget = None
                if hasattr(self.imported,'Widget'):
                    self.customWidget = self.imported.Widget(self)
                    self.boxlayout.addWidget(self.customWidget)
        except Exception:
            self._processHandler.error(traceback.format_exc())

    def loadfile(self):
        rendererScriptName = qw.QFileDialog.getOpenFileName(self,'Open File','./renderer',"GLSL rendering script (*.py)","",qw.QFileDialog.DontUseNativeDialog)
        rendererScriptName = rendererScriptName[0]
        self._load(rendererScriptName)

    def reload(self):
        self._load(self.rendererScriptName)

    def importModuleFromPath(self):
        try:
            spec = util.spec_from_file_location(self.rendererName, location=self.rendererScriptName)
            self.imported = util.module_from_spec(spec)
            sys.modules[self.rendererName] = self.imported
            spec.loader.exec_module(self.imported)
        except:
            self._processHandler.error(traceback.format_exc())

    def restartDisplay(self):
        self.suspendDisplay()
        while self._processHandler.get_state(self._displayProcName,'status') == 0:
            self._processHandler.set_state(self._displayProcName,'status',1)
        self.reload()
        self._processHandler.info("Restarted [{}] process".format(self._displayProcName))

    def suspendDisplay(self):
        while self._processHandler.get_state(self._displayProcName,'status') > 0:
            self._processHandler.set_state(self._displayProcName,'status',0)
        self._processHandler.info("Suspended [{}] process".format(self._displayProcName))

    def shutdown(self):
        while self._processHandler.get_state(self._displayProcName, "status") != -1:
            self._processHandler.set_state(self._displayProcName,"status",-11)
