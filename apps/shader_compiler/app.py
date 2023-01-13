from bin.app import AbstractGUIAPP, AbstractGLAPP
from compiler import GLProtocolCommander,GLProtocolCompiler

class ShaderCompilerGUI(AbstractGUIAPP):

    def initialize(self):
        super().initialize()
        self._win = GLProtocolCommander(self)
        self.info("Starting GUI")
        self._win.show()

class ShaderCompilerCanvas(AbstractGLAPP):
    def initialize(self):
        super().initialize()
        self._win = GLProtocolCompiler(self, app=self._app, refresh_interval=1,
                                       VS='./_shader/default.VS',
                                       FS='./_shader/default.FS')
        self.info('Starting OPENGL window')
        self._win.initialize()
        self._win.show()
