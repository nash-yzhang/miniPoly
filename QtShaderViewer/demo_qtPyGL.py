from miniPoly.core import BaseMinion,LoggerMinion
import logging
from vispy import gloo,app
import PyQt5.QtCore as qc
import PyQt5.QtWidgets as qw
import glsl_preset as gp
import traceback,sys,os
from importlib import util, reload

class GUICtrl(qw.QMainWindow):

    def __init__(self, processHandler, windowSize = (400,400), rendererName = None):
        super().__init__()
        self._processHandler = processHandler
        self.setWindowTitle("GLSL Controller")
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
                    self._processHandler.log(logging.INFO,"Reloaded rendering script {}".format(rendererScriptName))
                else:
                    self.rendererScriptName = rendererScriptName
                    self.rendererName = self.rendererScriptName.split("/")[-1][:-3]
                    self.importModuleFromPath()
                    self._processHandler.log(logging.INFO,"Loaded rendering script: {}".format(rendererScriptName))
                self._processHandler.log(logging.INFO,"Forwarding rendering script to [Display]")
                self._processHandler.send('Display',('rendering_script',rendererScriptName))
                if self.customWidget is not None:
                    self.boxlayout.removeWidget(self.customWidget)
                    self.customWidget = None
                if hasattr(self.imported,'customWidget'):
                    self.customWidget = self.imported.customWidget(self)
                    self.boxlayout.addWidget(self.customWidget)
        except Exception:
            self._processHandler.log(logging.ERROR,traceback.format_exc())

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

class GUI(BaseMinion):
    def main(self):
        app = qw.QApplication(sys.argv)
        w = GUICtrl(self, rendererName='planeAnimator.py', )
        self.log(logging.INFO,"Starting GUI")
        w.show()
        app.exec()
        self.shutdown()

class GLCanvas(gp.glCanvas):
    def __init__(self,handler,*args,**kwargs):
        super(GLCanvas, self).__init__(*args,**kwargs)
        self._processHandler = handler

    def on_timer(self, event):
        msg = self._processHandler.get('Controller')
        if msg[0] == 'rendering_script':
            self._processHandler.log(logging.INFO,"Received rendering script from [Controller]")
            self.rendererScriptName = msg[1]
            self.rendererName = self.rendererScriptName.split("/")[-1][:-3]
            self.importModuleFromPath()
            self._renderer = self.imported.Renderer(self)
            self.load(self._renderer)
            self._processHandler.log(logging.INFO,"Running script...")
        self.update()

    def importModuleFromPath(self):
        spec = util.spec_from_file_location(self.rendererName, location=self.rendererScriptName)
        self.imported = util.module_from_spec(spec)
        sys.modules[self.rendererName] = self.imported
        spec.loader.exec_module(self.imported)

class CanvasHandler(BaseMinion):
    def main(self):
        canvas = GLCanvas(self)
        canvas.show()
        app.run()
        self.shutdown()

if __name__ == "__main__":
    lm = LoggerMinion()
    gui = GUI('Controller')
    canvas = CanvasHandler('Display')
    gui.attach_logger(lm)
    canvas.attach_logger(lm)
    gui.add_target(canvas)
    gui.run()
    canvas.run()
    lm.run()
