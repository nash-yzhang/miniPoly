import sys
from time import perf_counter

from PyQt5 import QtWidgets as qw

from miniPoly.core.minion import TimerMinion


def apply_stylesheet(*args, **kwargs):
    """Apply qt-material lazily after QApplication has been created."""
    from qt_material import apply_stylesheet as qt_material_apply_stylesheet

    return qt_material_apply_stylesheet(*args, **kwargs)


class AbstractGUIAPP(TimerMinion):
    """Process shell that runs a Qt-based compiler inside a miniPoly timer minion.

    Owns the `QApplication`, drives its event loop from the timer tick, and
    shuts the whole minion tree down once every top-level window has closed.
    Unlike `AbstractAPP`, this does not subclass it: the compiler here is a Qt
    widget/window rather than a headless object, so construction, theming and
    the window-close-triggers-shutdown behavior are specific to this shell.
    """
    def __init__(
        self,
        name,
        compiler,
        refresh_interval=10,
        theme="dark_red.xml",
        **kwargs,
    ):
        """Store the compiler class, its kwargs, and the qt-material theme to apply."""
        super(AbstractGUIAPP, self).__init__(name, refresh_interval)
        self._param_to_compiler = kwargs
        self._compiler = compiler
        self._theme = theme

    def initialize(self):
        """Create the QApplication, apply the theme, then build and show the compiler.

        The `QApplication` must exist before any Qt widget is constructed, so it
        is created here rather than passed in like GL.py's VisPy `Application` --
        the compiler is instantiated directly afterwards instead of through
        `super().initialize()`, since this class does not subclass `AbstractAPP`.
        """
        self._app = qw.QApplication(sys.argv)
        if self._theme:
            apply_stylesheet(self._app, theme=self._theme)
        super().initialize()
        self._compiler = self._compiler(self, **self._param_to_compiler)
        self.info(f"GUI '{self.name}' initialized")
        self._compiler.show()

    def on_time(self,t):
        """Pump the Qt event loop, then check whether all windows have closed."""
        self._app.processEvents()
        self.poll_GUI_windows()

    #: Seconds shutdown() waits for the other minions to go down before giving up.
    SHUTDOWN_TIMEOUT = 10.0

    def poll_GUI_windows(self):
        """Trigger shutdown once every top-level Qt window has become invisible.

        Guards against the empty-list case (`any([])` is `False`): a tick that
        lands before any window has called `show()` must not be mistaken for
        "every window closed" and trigger an early exit (see B4 in the code
        comment below).
        """
        win_status = []
        for win in self._app.allWindows():
            win_status.append(win.isVisible())
        # `win_status` being empty is not the same as every window being hidden:
        # any([]) is False, so an on_time tick that landed before the window's show()
        # used to close the whole application. Seen as "sometimes it exits right after
        # starting" (B4).
        if win_status and not any(win_status):
            self.shutdown()

    def shutdown(self):
        """Ask every linked minion to stop, then wait (with a timeout) for them to go down.

        Bounded rather than an unconditional wait: a peer that crashed keeps
        reporting whatever status it last held, so `is_alive()` never goes False
        for it and an unbounded loop here could hang the whole program forever
        over one dead process (see B2 in the code comment below) -- giving up
        after `SHUTDOWN_TIMEOUT` and going down anyway is strictly better than
        that, since the peer's segments are reclaimed by the OS regardless.
        """
        def kill_minion(minion_name):
            """Tell one linked minion to stop by writing -1 to its shared status."""
            self.set_state_to(minion_name, 'status', -1)

        # Bounded. A crashed peer keeps reporting whatever its status segment last held,
        # so is_alive() never goes False for it and this used to be an unbreakable loop:
        # one crashed minion meant the program could not be closed and had to be killed
        # (B2). Giving up and going down is strictly better than hanging -- the peer is
        # already gone, and its segments are released by the OS.
        deadline = perf_counter() + self.SHUTDOWN_TIMEOUT
        while True:
            minion_status = self.poll_minion(kill_minion)
            if not any(minion_status):
                break
            if perf_counter() > deadline:
                self.error(
                    f"{sum(1 for s in minion_status if s)} of {len(minion_status)} minion(s) did not "
                    f"go down within {self.SHUTDOWN_TIMEOUT:.0f} s; shutting down anyway. A minion that "
                    f"crashed still looks alive to its peers."
                )
                break

        self.status = -1
