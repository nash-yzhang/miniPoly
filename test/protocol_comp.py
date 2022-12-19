from bin.app import AbstractAPP
from bin.minion import BaseMinion, LoggerMinion
from apps.protocol_compiler.protocol_compiler import ProtocolCommander, GraphicProtocolCompiler, ServoDriver
from multiprocessing import Lock

class TestGUI(AbstractAPP):

    def initialize(self):
        super().initialize()
        self._win = ProtocolCommander(self)
        self.info("Starting GUI")
        self._win.show()


class CanvasModule(AbstractAPP):

    def initialize(self):
        super().initialize()
        self._win = GraphicProtocolCompiler(self)
        self.info('Starting display window')
        self._win.initialize()
        self._win.show()



if __name__ == '__main__':
    lock = Lock()
    GUI = TestGUI('testgui',lock=lock)
    GL_canvas = CanvasModule('OPENGL',lock=lock)
    servo = ServoDriver('servo',lock=lock)
    GL_canvas.connect(GUI)
    GUI.connect(servo)
    logger = LoggerMinion('TestGUI logger',lock=lock)
    GUI.attach_logger(logger)
    GL_canvas.attach_logger(logger)
    servo.attach_logger(logger)
    logger.run()
    servo.run()
    GUI.run()
    GL_canvas.run()
