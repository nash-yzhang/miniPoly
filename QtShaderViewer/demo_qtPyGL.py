from miniPoly.core import BaseMinion,LoggerMinion
import logging
from vispy import gloo,app
from time import sleep
import numpy as np
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
        restartDisplay = qw.QAction("Restart Display",self)
        restartDisplay.setShortcut("Ctrl+Shift+R")
        restartDisplay.setStatusTip("Restart display process")
        restartDisplay.triggered.connect(self.restartDisplay)
        self._menu_file.addAction(loadfile)
        self._menu_file.addAction(reload)
        self._menu_file.addAction(restartDisplay)
        self._vcanvas = None
        self.rendererName = ''
        self.rendererScriptName = ''
        self.central_widget = qw.QWidget()               # define central widget
        self.setCentralWidget(self.central_widget)
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
                self._processHandler.log(logging.INFO,"Forwarding script [{}] to [Display]".format(rendererScriptName))
                self._processHandler.send('Display',('rendering_script',rendererScriptName))
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

    def restartDisplay(self):
        while self._processHandler.get_state('Display','status') > 0:
            self._processHandler.set_state('Display','status',0)
        while self._processHandler.get_state('Display','status') == 0:
            self._processHandler.set_state('Display','status',1)
        self.reload()
        self._processHandler.log(logging.INFO,"Restarted [Display] process")



class GUI(BaseMinion):
    def __init__(self,*args,**kwargs):
        super(GUI, self).__init__(*args,**kwargs)
    
    def main(self):
        app = qw.QApplication(sys.argv)
        w = GUICtrl(self, rendererName='planeAnimator.py', )
        self.log(logging.INFO,"Starting GUI")
        w.show()
        app.exec()
        self.shutdown()

    def shutdown(self):
        for tgt in self.target.keys():
            while self.get_state(tgt, "status") != -1:
                self.set_state(tgt, "status", -1)
        self.set_state(self.name, "status", -1)


class GLCanvas(gp.glCanvas):
    def __init__(self,handler,*args,**kwargs):
        super(GLCanvas, self).__init__(*args,**kwargs)
        self._processHandler = handler
        self._setTime = 0
        self._tic = 0
        self._rmtShutdown = False

    def on_close(self):
        self._processHandler.set_state(self._processHandler.name,'status',0)

    def on_timer(self, event):
        if self.timer.elapsed - self._setTime > 1:
            self._setTime = np.floor(self.timer.elapsed)
            msg = self._processHandler.get('Controller')
            if msg is not None:
                if msg[0] == 'rendering_script':
                    self.rendererScriptName = msg[1]
                    self.rendererName = self.rendererScriptName.split("/")[-1][:-3]
                    self._processHandler.log(logging.INFO,"Received rendering script [{}] from [Controller]".format(self.rendererScriptName))
                    self.importModuleFromPath()
                    self._renderer = self.imported.Renderer(self)
                    self.load(self._renderer)
                    self._processHandler.log(logging.INFO,"Running script [{}]".format(self.rendererScriptName))
        self.update()
        if self._processHandler.get_state()==-1:
            self._rmtShutdown = True
            self.on_close()

    def on_close(self):
        if not self._rmtShutdown:
            self._processHandler.set_state(self._processHandler.name,'status',0)
        self.close()

    def importModuleFromPath(self):
        spec = util.spec_from_file_location(self.rendererName, location=self.rendererScriptName)
        self.imported = util.module_from_spec(spec)
        sys.modules[self.rendererName] = self.imported
        spec.loader.exec_module(self.imported)

class CanvasHandler(BaseMinion):
    def main(self):
        cvs = GLCanvas(self)
        self.set_state(self.name,'status',2)
        cvs.show()
        app.run()
        cvs.on_close()



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
