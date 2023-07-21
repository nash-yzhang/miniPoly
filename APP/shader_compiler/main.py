from compiler import GLProtocolCompiler, GLProtocolCommander
from miniPoly.prototype.Logging import LoggerMinion
from miniPoly.prototype.GL import AbstractGLAPP
from miniPoly.prototype.GUI import AbstractGUIAPP

if __name__ == '__main__':
    GUI = AbstractGUIAPP('GUI',GLProtocolCommander,refresh_interval=1)
    GL_canvas = AbstractGLAPP('OPENGL',GLProtocolCompiler, VS='./_shader/default.VS',
                   FS='./_shader/default.FS')
    GL_canvas.connect(GUI)
    logger = LoggerMinion('TestGUI logger')
    GUI.attach_logger(logger)
    GL_canvas.attach_logger(logger)
    logger.run()
    GL_canvas.run()
    GUI.run()
