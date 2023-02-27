from bin.app import AbstractGUIAPP, AbstractGLAPP
from compiler import GLProtocolCommander, GLProtocolCompiler


class ShaderCompilerGUI(AbstractGUIAPP):

    def initialize(self):
        super().initialize()
        self._win = GLProtocolCommander(self)
        self.info("Starting GUI")
        self._win.show()


class ShaderCompilerCanvas(AbstractGLAPP):

    def __init__(self, *args, VS='./_shader/default.VS',
                   FS='./_shader/default.FS', **kwargs):
        interval = kwargs.pop('interval', 1)
        super().__init__(*args, refresh_interval=interval)
        self._VS = VS
        self._FS = FS
        self._GLWinKwargs = kwargs
        self._win = None

    def initialize(self,):
        super().initialize()
        self._win = GLProtocolCompiler(self, app=self._app, VS=self._VS, FS=self._FS, **self._GLWinKwargs)
        self.info('Starting OPENGL window')
        self._win.initialize()
        self._win.show()
