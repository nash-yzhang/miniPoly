from app import ShaderCompilerGUI, ShaderCompilerCanvas
from bin.app.prototypes import LoggerMinion

if __name__ == '__main__':
    GUI = ShaderCompilerGUI('GUI',refresh_interval=1)
    GL_canvas = ShaderCompilerCanvas('OPENGL',refresh_interval=1)
    GL_canvas.connect(GUI)
    logger = LoggerMinion('TestGUI logger')
    GUI.attach_logger(logger)
    GL_canvas.attach_logger(logger)
    logger.run()
    GL_canvas.run()
    GUI.run()
