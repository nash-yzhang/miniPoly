from bin.minion import BaseMinion,TimerMinion
import sys
from time import time
from vispy import app
import vispy
import PyQt5.QtWidgets as qw
from bin.gui import BaseGUI
from bin.display import GLDisplay

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

class GUIAPP(AbstractAPP):

    def __init__(self, *args, **kwargs):
        super(GUIAPP, self).__init__(*args, **kwargs)
        self._win = None

    def initialize(self):
        super().initialize()
        self._win = self._compiler
        self._win.show()

class StreamingAPP(AbstractAPP):

    def __init__(self, *args, timer_minion=None, trigger_minion=None, **kwargs):
        super(StreamingAPP, self).__init__(*args, **kwargs)

        if timer_minion is None:
            self.error(f"{self.name} could not be created because the '[timer_minion]' is not set")
            return None

        if trigger_minion is None:
            self.error(f"{self.name} could not be created because the '[trigger_minion]' is not set")
            return None

        self._param_to_compiler['timer_minion'] = timer_minion
        self._param_to_compiler['trigger_minion'] = trigger_minion



class AbstractGLAPP(TimerMinion):
    def __init__(self, *args, **kwargs):
        super(AbstractGLAPP, self).__init__(*args, **kwargs)
    def initialize(self):
        self._app = vispy.app.application.Application(backend_name='PyQt5')
        super().initialize()

    def on_time(self,t):
        self._app.process_events()


class AbstractGUIAPP(TimerMinion):
    def __init__(self, *args, **kwargs):
        super(AbstractGUIAPP, self).__init__(*args, **kwargs)

    def initialize(self):
        self._app = qw.QApplication(sys.argv)
        super().initialize()

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
