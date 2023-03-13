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
    def __init__(self, *args, **kwargs):
        super(AbstractAPP, self).__init__(*args, **kwargs)
        self._param_to_compiler = {}
        self._compiler = None


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

# class APP(AbstractAPP):
#     def __init__(self, *args, **kwargs):
#         super(APP, self).__init__(*args, **kwargs)
#         self.display_proc = None
#
#     @property
#     def display_proc(self):
#         return self._displayProcName
#
#     @display_proc.setter
#     def display_proc(self, display_proc_name):
#         self._displayProcName = display_proc_name
#
#     def gui_init(self):
#         self._win = BaseGUI(self, rendererPath='renderer/planeTexRenderer.py')
#         if not self.display_proc:
#             self.warning("[{}] Undefined display process name".format(self.name))
#         else:
#             self._win.display_proc = self.display_proc
#
#     def gui_close(self):
#         def kill_minion(minion_name):
#             self.set_state_to(minion_name, 'status', -11)
#
#         safe_to_shutdown = False
#         while not safe_to_shutdown:
#             minion_status = self.poll_minion(kill_minion)
#             if not any(minion_status):
#                 safe_to_shutdown = True