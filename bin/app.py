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
        for tgt in self._conn.keys():
            while self.get_state_from(tgt, "status") != -1:
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
        self._connections = {}
        self._shared_memory = {}
        self._shared_memory_param = {}

        self.create_shared_memory('GUI',shape=(10,), dtype=np.float64)
        self.create_shared_memory('OPENGL',shape=(10,), dtype=np.float64)
        self.create_shared_memory('MAIN LOGGER',shape=(10,), dtype=np.float64)

        self._GUI = GUIModule('GUI')
        self._GUI.link_shared_memory(*self._shared_memory_param['GUI'])
        self._GL_canvas = CanvasModule('OPENGL')
        self._GL_canvas.link_shared_memory(*self._shared_memory_param['OPENGL'])

        self._GUI.display_proc = self._GL_canvas.name
        self._GL_canvas.controller_proc = self._GUI.name
        self._logger = LoggerMinion('MAIN LOGGER')
        self._logger.link_shared_memory(*self._shared_memory_param['MAIN LOGGER'])
        self._logger.link_shared_memory(*self._shared_memory_param['GUI'])
        self._logger.link_shared_memory(*self._shared_memory_param['OPENGL'])

        self._logger.set_level(self._GUI.display_proc,'debug')
        self._GUI.attach_logger(self._logger)
        self._GL_canvas.attach_logger(self._logger)
        self.connect(self._GUI,self._GL_canvas)

    def log(self, *args):
        self._logger.log(*args)

    def create_shared_memory(self,name,shape,dtype):
        proto_shared_memory = np.ndarray(shape=shape, dtype=dtype)
        self._shared_memory[name] = shared_memory.SharedMemory(create=True,name=name,size=proto_shared_memory.nbytes)
        self._shared_memory_param[name] = (name,shape,dtype)

    def connect(self, source, target):
        source.add_connection(target)
        source.link_shared_memory(*self._shared_memory_param[target.name])
        target.link_shared_memory(*self._shared_memory_param[source.name])
        if source.name not in self._connections.keys():
            self._connections[source.name] = [target.name]
        else:
            self._connections[source.name].append(target.name)
        self.log(logging.INFO, "[{}] Connection [{} -> {}] has been set up".format(self.name, source.name, target.name))

        # if conn_type == "mutual":
        #     target.add_connection(source)
        #     if target.name not in self._connections.keys():
        #         self._connections[target.name] = [source.name]
        #
        #     else:
        #         self._connections[target.name].append(source.name)
        #     self.log(logging.INFO,
        #              "[{}] Connection [{} -> {}] has been set up".format(self.name, target.name, source.name))
        # elif conn_type == "uni":
        #     pass
        # else:
        #     self.log(logging.INFO,
        #              "[{}] Failed to setup connection: Unknown connection type '{}'".format(self.name, conn_type))

    def run(self):
        self._GUI.run()
        self._GL_canvas.run()
        self._logger.run()
