from miniPoly.core.minion import TimerMinion


# from miniPoly.gui import BaseGUI
# from miniPoly.display import GLDisplay

class AbstractAPP(TimerMinion):
    """Process shell that owns a compiler class and builds it inside the child process.

    Structurally just a `TimerMinion`; kept as its own class so the process-shell
    layer (GL/GUI/Streaming) has a common base to subclass and to type-check
    against, and so the compiler-construction step in `initialize()` lives in one
    place instead of being duplicated by every concrete shell.
    """
    # The same as TimerMinion, just for reference structural clarity
    def __init__(self, name, compiler, refresh_interval=10, **kwargs):
        """Store the compiler class and its constructor kwargs for later.

        The compiler is not instantiated here: `__init__` still runs in the
        parent process, while the compiler (and anything it touches, e.g. a Qt
        or VisPy app) must be built inside the child process, which happens in
        `initialize()`.
        """
        super(AbstractAPP, self).__init__(name, refresh_interval)
        self._param_to_compiler = kwargs
        self._compiler = compiler

    def initialize(self):
        """Build the compiler in-process, replacing the stored class with the instance.

        A construction failure is logged and swallowed rather than raised, so a
        broken compiler does not crash the child process's startup path -- it
        just leaves `self._compiler` as the un-instantiated class.
        """
        super().initialize()
        try:
            self._compiler = self._compiler(self, **self._param_to_compiler)
        except Exception as e:
            self.error(f"{self.name} could not be created because of {e}")
            return None
        self.info(f"{self.name} initialized")


