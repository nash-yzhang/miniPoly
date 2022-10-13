from bin.minion import BaseMinion,LoggerMinion
import logging,sys
from vispy import app
import vispy
import PyQt5.QtWidgets as qw
from bin.GUI import GUICtrl
from bin.Display import GLDisplay

class GUIModule(BaseMinion):
    def __init__(self,*args,**kwargs):
        super(GUIModule, self).__init__(*args,**kwargs)

    def main(self):
        app = qw.QApplication(sys.argv)
        w = GUICtrl(self, rendererName='renderer/planeAnimator.py', )
        self.log(logging.INFO,"Starting GUI")
        w.show()
        app.exec()
        self.shutdown()

    def shutdown(self):
        for tgt in self.target.keys():
            while self.get_state(tgt, "status") != -1:
                self.set_state(tgt, "status", -1)
        self.set_state(self.name, "status", -1)

class CanvasModule(BaseMinion):
    def main(self):
        try:
            vispy.use('glfw')
            cvs = GLDisplay(self)
            cvs.show()
            app.run()
            cvs.on_close()
        except Exception as e:
            self.error(e)

class GLapp:
    def __int__(self,name):
        self.name = name
        self._GUI = GUIModule('MAIN GUI')
        self._GL_canvas = CanvasModule('GL_CANVAS')
        self._logger = LoggerMinion('MAIN LOGGER')
        self._GUI.attach_logger(self._logger)
        self._GL_canvas.attach_logger(self._logger)
        self._connections = {}

    def log(self,*args):
        self.loger.log(*args)

    def connect(self, source, target, conn_type="uni"):
        source.add_target(target)
        if source.name not in self._connections.keys():
            self._connections[source.name] = [target.name]
        else:
            self._connections[source.name].append(target.name)
        self.log(logging.INFO,"[{}] Connection [{} -> {}] has been set up".format(self.name,source.name,target.name))

        if conn_type == "mutual":
            target.add_target(source)
            if target.name not in self._connections.keys():
                self._connections[target.name] = [source.name]

            else:
                self._connections[target.name].append(source.name)
            self.log(logging.INFO,"[{}] Connection [{} -> {}] has been set up".format(self.name,target.name,source.name))
        elif conn_type == "uni":
            pass
        else:
            self.log(logging.INFO,"[{}] Failed to setup connection: Unknown connection type '{}'".format(self.name, conn_type))

    def run(self):
        self._GUI.run()
        self._GL_canvas.run()
        self._logger.run()

