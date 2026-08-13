from vispy.app.application import Application
from miniPoly.processor.prototypes import AbstractAPP


class StreamingAPP(AbstractAPP):
    """Process shell for a compiler that needs a timer minion and a trigger minion.

    Both are required collaborators (e.g. for pacing acquisition and reacting
    to external triggers) rather than optional kwargs, so their names are
    forwarded into `_param_to_compiler` explicitly instead of just being part
    of `**kwargs`, and their absence is reported instead of failing later with
    an unrelated `KeyError` inside the compiler.
    """

    def __init__(self, *args, timer_minion=None, trigger_minion=None, **kwargs):
        """Validate that a timer minion and trigger minion were supplied, then store them."""
        super(StreamingAPP, self).__init__(*args, **kwargs)

        if timer_minion is None:
            self.error(f"{self.name} could not be created because the '[timer_minion]' is not set")
            return None

        if trigger_minion is None:
            self.error(f"{self.name} could not be created because the '[trigger_minion]' is not set")
            return None

        self._param_to_compiler['timer_minion'] = timer_minion
        self._param_to_compiler['trigger_minion'] = trigger_minion

class StreamingGLAPP(StreamingAPP):
    """`StreamingAPP` plus a VisPy canvas/app, combining Streaming's and GL's process shells."""

    def __init__(self, *args, timer_minion=None, trigger_minion=None, gl_backend='PyQt5', **kwargs):
        """Record the VisPy backend; `StreamingAPP` handles the timer/trigger minions.

        Both minions are forwarded explicitly rather than left to `**kwargs`, because
        naming them as parameters here would otherwise swallow them: `StreamingAPP`
        would then validate its own `None` defaults, log two spurious "could not be
        created" errors and bail out of its own `__init__` before storing anything, and
        this class would have to repeat the same validation to undo the damage.
        """
        super(StreamingGLAPP, self).__init__(*args, timer_minion=timer_minion,
                                             trigger_minion=trigger_minion, **kwargs)
        self._gl_backend = gl_backend

    def initialize(self):
        """Create the VisPy app, build the compiler, then show it (see GL.py's `GLAPP`)."""
        self._app = Application(backend_name=self._gl_backend)
        super().initialize()
        self._compiler.show()

    def on_time(self,t):
        """Pump VisPy's event loop once per timer tick."""
        self._app.process_events()

