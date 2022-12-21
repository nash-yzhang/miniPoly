from bin.app import AbstractAPP
from bin.minion import LoggerMinion
from bin.compiler import ProtocolCommander, GraphicProtocolCompiler, ServoDriver
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
    GUI = TestGUI('testgui')
    GL_canvas = CanvasModule('OPENGL')
    servo = ServoDriver('servo')
    GL_canvas.connect(GUI)
    GUI.connect(servo)
    logger = LoggerMinion('TestGUI logger')
    GUI.attach_logger(logger)
    GL_canvas.attach_logger(logger)
    servo.attach_logger(logger)
    logger.run()
    servo.run()
    GUI.run()
    GL_canvas.run()
