import numpy as np

from bin.minion import BaseMinion, LoggerMinion
from multiprocessing import shared_memory
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
        def kill_minion(minion_name):
            self.set_state_to(minion_name,'status',-1)
        safe_to_shutdown = False
        while not safe_to_shutdown:
            minion_status = self.poll_minion(kill_minion)
            if not any(minion_status):
                safe_to_shutdown = True
        self.set_state_to(self.name, "status", -1)


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
        self._connections = {}
        self._shared_memory = {}
        self._shared_memory_param = {}

        self._GUI = GUIModule('GUI')
        self._GL_canvas = CanvasModule('OPENGL')
        self._GL_canvas.connect(self._GUI)

        self._GUI.display_proc = self._GL_canvas.name
        self._GL_canvas.controller_proc = self._GUI.name
        self._logger = LoggerMinion('MAIN LOGGER')

        self._GUI.attach_logger(self._logger)
        self._GL_canvas.attach_logger(self._logger)
        self._logger.set_level(self._GL_canvas.name,'debug')

    def log(self, *args):
        self._logger.log(*args)

    def run(self):
        self._GUI.run()
        self._GL_canvas.run()
        self._logger.run()
