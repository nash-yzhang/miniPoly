import PyQt5.QtWidgets as qw
import PyQt5.QtCore as qc
import traceback, sys
from importlib import util, reload

from bin.minion import AbstractMinionMixin

class BaseGUI(qw.QMainWindow, AbstractMinionMixin):
    '''
    Base class serving as an interface between "minion" process handler and Qt GUI
    '''
    def __init__(self, processHandler=None, windowSize=(400, 400), rendererPath=None):
        super().__init__()
        self._processHandler = processHandler
        self._windowSize = windowSize

        self._displayProcName = ''
        self.rendererName = ''
        self._renderer_path = ''
        self._vcanvas = None

        self._init_main_win()
        self._init_menu()

        self.load_renderer(rendererPath)

    def _init_main_win(self):
        self.setWindowTitle("Main")
        self.resize(*self._windowSize)

    def _init_menu(self):
        self._menubar = self.menuBar()
        self._menu_file = self._menubar.addMenu('File')
        self._menu_display = self._menubar.addMenu('Display')
        loadfile = qw.QAction("Load", self)
        loadfile.setShortcut("Ctrl+O")
        loadfile.setStatusTip("Load renderer script")
        loadfile.triggered.connect(self.loadfile)
        reload = qw.QAction("Reload", self)
        reload.setShortcut("Ctrl+R")
        reload.setStatusTip("Reload renderer")
        reload.triggered.connect(self.reload)
        Exit = qw.QAction("Quit", self)
        Exit.setShortcut("Ctrl+Q")
        Exit.setStatusTip("Exit program")
        Exit.triggered.connect(self.close)
        restartDisplay = qw.QAction("Restart Display", self)
        restartDisplay.setShortcut("Ctrl+Shift+R")
        restartDisplay.setStatusTip("Restart display process")
        restartDisplay.triggered.connect(self.restartDisplay)
        haltDisplay = qw.QAction("Suspend Display", self)
        haltDisplay.setShortcut("Ctrl+Shift+H")
        haltDisplay.setStatusTip("Suspend display process")
        haltDisplay.triggered.connect(self.suspendDisplay)
        self._menu_file.addAction(loadfile)
        self._menu_file.addAction(Exit)
        self._menu_display.addAction(restartDisplay)
        self._menu_display.addAction(haltDisplay)
        self.central_widget = qw.QWidget()  # define central widget
        self.setCentralWidget(self.central_widget)
        self.boxlayout = qw.QVBoxLayout()
        self.central_widget.setLayout(self.boxlayout)
        self.canvasLabel = qw.QLabel("Load stimulus via File (Ctrl+O)")
        self.canvasLabel.setAlignment(qc.Qt.AlignCenter)
        self.boxlayout.addWidget(self.canvasLabel)
        self.customWidget = None

    @property
    def display_proc(self):
        return self._displayProcName

    @display_proc.setter
    def display_proc(self, display_proc_name):
        self._displayProcName = display_proc_name
        self._load()

    def load_renderer(self, renderer_path):
        if renderer_path:
            self._renderer_path = renderer_path
            self._load()
        else:
            self._processHandler.error("Undefined renderer path")

    def _load(self):
        try:
            if self._displayProcName:
                if self._renderer_path:
                    if self._renderer_path == self._renderer_path:
                        self.importModuleFromPath()
                        self._processHandler.info("Reloaded rendering script {}".format(self._renderer_path))
                    else:
                        self._renderer_path = self._renderer_path
                        self.rendererName = self._renderer_path.split("/")[-1][:-3]
                        self.importModuleFromPath()
                        self._processHandler.info("Loaded rendering script: {}".format(self._renderer_path))
                    self._processHandler.info(
                        "Forwarding script [{}] to [{}]".format(self._renderer_path, self._displayProcName))
                    self.send(self._displayProcName, 'rendering_script', self._renderer_path)
                    # Load GUI
                    if self.customWidget is not None:
                        self.customWidget.close()
                        self.boxlayout.removeWidget(self.customWidget)
                        self.customWidget = None
                    if hasattr(self.imported, 'Widget'):
                        self.customWidget = self.imported.Widget(self)
                        self.boxlayout.addWidget(self.customWidget)
                else:
                    self._processHandler.log("Display process undefined")
        except Exception:
            self._processHandler.error(traceback.format_exc())

    def loadfile(self):
        rendererScriptName = qw.QFileDialog.getOpenFileName(self, 'Open File', './renderer',
                                                            "GLSL rendering script (*.py)", "",
                                                            qw.QFileDialog.DontUseNativeDialog)
        self.load_renderer(rendererScriptName[0])

    def reload(self):
        if self._renderer_path:
            self._load()
        else:
            self._processHandler.error('Failed to reload: invalid renderer path')

    def importModuleFromPath(self):
        try:
            spec = util.spec_from_file_location(self.rendererName, location=self._renderer_path)
            self.imported = util.module_from_spec(spec)
            sys.modules[self.rendererName] = self.imported
            spec.loader.exec_module(self.imported)
        except:
            self._processHandler.error(traceback.format_exc())

    def restartDisplay(self):
        self.suspendDisplay()
        while self._processHandler.get_state(self._displayProcName, 'status') == 0:
            self._processHandler.set_state(self._displayProcName, 'status', 1)
        self.reload()
        self._processHandler.info("Restarted [{}] process".format(self._displayProcName))

    def suspendDisplay(self):
        while self._processHandler.get_state(self._displayProcName, 'status') > 0:
            self._processHandler.set_state(self._displayProcName, 'status', 0)
        self._processHandler.info("Suspended [{}] process".format(self._displayProcName))

    def shutdown(self):
        while self._processHandler.get_state(self._displayProcName, "status") != -1:
            self._processHandler.set_state(self._displayProcName, "status", -11)
