from bin.app import AbstractGUIModule
from bin.minion import BaseMinion, LoggerMinion
from apps.protocol_compiler.protocol_compiler import ProtocolCommander, GraphicProtocolCompiler, ServoDriver
from vispy import gloo, app
from multiprocessing import Lock

class TestGUI(AbstractGUIModule):

    def gui_init(self):
        self._win = ProtocolCommander(self)



class CanvasModule(BaseMinion):
    def __init__(self, *args, **kwargs):
        super(CanvasModule, self).__init__(*args, **kwargs)
        self._win = None

    def main(self):
        try:
            self._win = GraphicProtocolCompiler(self)
            self._win.initialize()
            self._win.show()
            self.info('Starting display window')
            app.run()
            self._win.on_close()
        except Exception as e:
            self.error(e)



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
