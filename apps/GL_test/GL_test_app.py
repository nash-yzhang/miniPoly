from bin.widgets.prototypes import APP, CanvasModule
from bin.minion import LoggerMinion
from multiprocessing import Lock
class GLapp:
    def __init__(self, name):
        self.name = name
        self._lock = Lock()
        self._connections = {}
        self._shared_memory = {}
        self._shared_memory_param = {}

        self._GUI = APP('GUI', lock=self._lock)
        self._GL_canvas = CanvasModule('OPENGL',lock=self._lock)
        self._GL_canvas.connect(self._GUI)

        self._GUI.display_proc = self._GL_canvas.name
        self._GL_canvas.controller_proc = self._GUI.name
        self._logger = LoggerMinion('MAIN LOGGER',lock=self._lock)

        self._GUI.attach_logger(self._logger)
        self._GL_canvas.attach_logger(self._logger)
        self._logger.set_level(self._GL_canvas.name,'debug')

    def log(self, *args):
        self._logger.log(*args)

    def run(self):
        self._GUI.run()
        self._GL_canvas.run()
        self._logger.run()
