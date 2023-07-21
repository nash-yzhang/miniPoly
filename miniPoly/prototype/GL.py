import vispy

from miniPoly.process.minion import TimerMinion


class AbstractGLAPP(TimerMinion):
    def __init__(self, name, compiler, refresh_interval=10, **kwargs):
        super(AbstractGLAPP, self).__init__(name, refresh_interval)
        self._param_to_compiler = kwargs
        self._compiler = compiler

    def initialize(self):
        self._app = vispy.app.application.Application(backend_name='PyQt5')
        super().initialize()
        self._compiler = self._compiler(self, **self._param_to_compiler)
        self._compiler.initialize()
        self.info(f"OpenGL app '{self.name}' initialized")
        self._compiler.show()

    def on_time(self,t):
        self._app.process_events()
