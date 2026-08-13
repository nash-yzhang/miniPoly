"""Generic VisPy process shell for canvas-based compilers."""

from vispy.app.application import Application

from miniPoly.processor.prototypes import AbstractAPP


class GLAPP(AbstractAPP):
    """Run a VisPy canvas compiler inside a miniPoly timer minion."""

    def __init__(self, *args, gl_backend="PyQt5", **kwargs):
        """Remember which VisPy backend to create the canvas app with."""
        super().__init__(*args, **kwargs)
        self._gl_backend = gl_backend

    def initialize(self):
        """Create the VisPy app, hand it to the compiler, then build and show the canvas.

        The app is created before `super().initialize()` (which instantiates the
        compiler) because the compiler's canvas construction needs a running
        `Application` to attach to; it is passed in via `_param_to_compiler`
        rather than a constructor argument so compilers that don't care about it
        are unaffected.
        """
        self._app = Application(backend_name=self._gl_backend)
        self._param_to_compiler.setdefault("app", self._app)
        super().initialize()
        self._compiler.show()

    def on_time(self, t):
        """Pump VisPy's event loop once per timer tick."""
        self._app.process_events()
