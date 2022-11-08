from bin.minion import BaseMinion, LoggerMinion
import logging, sys
from vispy import app
import vispy
import PyQt5.QtWidgets as qw
from bin.GUI import BaseGUI
from bin.Display import GLDisplay

class GUIModule(BaseMinion):
    def __init__(self, *args, **kwargs):
        super(GUIModule, self).__init__(*args, **kwargs)

        self._app = None
        self._win = None
        self.display_proc = None

    @property
    def display_proc(self):
        return self._displayProcName

    @display_proc.setter
    def display_proc(self, display_proc_name):
        self._displayProcName = display_proc_name

    def main(self):
        self._app = qw.QApplication(sys.argv)
        self._win = BaseGUI(self, rendererPath='renderer/visTac.py')
        if not self.display_proc:
            self.warning("[{}] Undefined display process name".format(self.name))
        else:
            self._win.display_proc = self.display_proc
        self.info("Starting GUI")
        self._win.show()
        self._app.exec()
        self.shutdown()

    def shutdown(self):
        for tgt in self.target.keys():
            while self.get_state(tgt, "status") != -1:
                self.set_state(tgt, "status", -1)
        self.set_state(self.name, "status", -1)


class CanvasModule(BaseMinion):
    def __init__(self, *args, **kwargs):
        super(CanvasModule, self).__init__(*args, **kwargs)
        self._win = None
        self.controller_proc = None

    def main(self):
        try:
            vispy.use('glfw')
            self._win = GLDisplay(self)
            if self.controller_proc is not None:
                self._win.controllerProcName = self.controller_proc
                self._win.show()
                self.info('Starting display window')
                app.run()
                self._win.on_close()
            else:
                self.error("[{}] Cannot initialize: Undefined controller process name".format(self.name))
        except Exception as e:
            self.error(e)

    @property
    def controller_proc(self):
        return self._controllerProcName

    @controller_proc.setter
    def controller_proc(self, value):
        self._controllerProcName = value


class GLapp:
    def __init__(self, name):
        self.name = name
        self._GUI = GUIModule('GUI')
        self._GL_canvas = CanvasModule('OPENGL')
        self._GUI.display_proc = self._GL_canvas.name
        self._GL_canvas.controller_proc = self._GUI.name
        self._logger = LoggerMinion('MAIN LOGGER')
        self._logger.set_level(self._GUI.display_proc,'debug')
        self._GUI.attach_logger(self._logger)
        self._GL_canvas.attach_logger(self._logger)
        self._connections = {}
        self.connect(self._GUI,self._GL_canvas)

    def log(self, *args):
        self._logger.log(*args)

    def connect(self, source, target, conn_type="uni"):
        source.add_target(target)
        if source.name not in self._connections.keys():
            self._connections[source.name] = [target.name]
        else:
            self._connections[source.name].append(target.name)
        self.log(logging.INFO, "[{}] Connection [{} -> {}] has been set up".format(self.name, source.name, target.name))

        if conn_type == "mutual":
            target.add_target(source)
            if target.name not in self._connections.keys():
                self._connections[target.name] = [source.name]

            else:
                self._connections[target.name].append(source.name)
            self.log(logging.INFO,
                     "[{}] Connection [{} -> {}] has been set up".format(self.name, target.name, source.name))
        elif conn_type == "uni":
            pass
        else:
            self.log(logging.INFO,
                     "[{}] Failed to setup connection: Unknown connection type '{}'".format(self.name, conn_type))

    def run(self):
        self._GUI.run()
        self._GL_canvas.run()
        self._logger.run()
