from miniPoly.core.minion import TimerMinion


# from miniPoly.gui import BaseGUI
# from miniPoly.display import GLDisplay

class AbstractAPP(TimerMinion):
    # The same as TimerMinion, just for reference structural clarity
    def __init__(self, name, compiler, refresh_interval=10, **kwargs):
        super(AbstractAPP, self).__init__(name, refresh_interval)
        self._param_to_compiler = kwargs
        self._compiler = compiler

    def initialize(self):
        super().initialize()
        try:
            self._compiler = self._compiler(self, **self._param_to_compiler)
        except Exception as e:
            self.error(f"{self.name} could not be created because of {e}")
            return None
        self.info(f"{self.name} initialized")


