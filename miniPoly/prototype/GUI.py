import sys

from PyQt5 import QtWidgets as qw
from qt_material import apply_stylesheet

from miniPoly.process.minion import TimerMinion


class AbstractGUIAPP(TimerMinion):
    def __init__(self, name, compiler, refresh_interval=10, **kwargs):
        super(AbstractGUIAPP, self).__init__(name, refresh_interval)
        self._param_to_compiler = kwargs
        self._compiler = compiler

    def initialize(self):
        self._app = qw.QApplication(sys.argv)
        apply_stylesheet(self._app, theme='dark_red.xml')
        super().initialize()
        self._compiler = self._compiler(self, **self._param_to_compiler)
        self.info(f"GUI '{self.name}' initialized")
        self._compiler.show()

    def on_time(self,t):
        self._app.processEvents()
        self.poll_GUI_windows()

    def poll_GUI_windows(self):
        win_status = []
        for win in self._app.allWindows():
            win_status.append(win.isVisible())
        if not any(win_status):
            self.shutdown()

    def shutdown(self):
        def kill_minion(minion_name):
            self.set_state_to(minion_name, 'status', -1)

        safe_to_shutdown = False
        while not safe_to_shutdown:
            minion_status = self.poll_minion(kill_minion)
            if not any(minion_status):
                safe_to_shutdown = True

        self.status = -1
