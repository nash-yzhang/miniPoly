from bin.minion import BaseMinion
import sys
from time import time
from vispy import app
import vispy
import PyQt5.QtWidgets as qw
from bin.gui import BaseGUI
from bin.display import GLDisplay

class AbstractGUIModule(BaseMinion):
    def __init__(self, *args, **kwargs):
        super(AbstractGUIModule, self).__init__(*args, **kwargs)

        self._app = None
        self._win = None

    def main(self):
        self._app = qw.QApplication(sys.argv)
        self._win = BaseGUI(self)
        self.gui_init()
        self.info("Starting GUI")
        self._win.show()
        self._app.exec()
        self.shutdown()

    def gui_init(self):
        pass
    def shutdown(self):
        self.gui_close()
        self.status = -1

    def gui_close(self):
        pass

class GUIModule(AbstractGUIModule):
    def __init__(self, *args, **kwargs):
        super(GUIModule, self).__init__(*args, **kwargs)
        self.display_proc = None

    @property
    def display_proc(self):
        return self._displayProcName

    @display_proc.setter
    def display_proc(self, display_proc_name):
        self._displayProcName = display_proc_name

    def gui_init(self):
        self._win = BaseGUI(self, rendererPath='renderer/planeTexRenderer.py')
        if not self.display_proc:
            self.warning("[{}] Undefined display process name".format(self.name))
        else:
            self._win.display_proc = self.display_proc

    def gui_close(self):
        def kill_minion(minion_name):
            self.set_state_to(minion_name, 'status', -11)

        safe_to_shutdown = False
        while not safe_to_shutdown:
            minion_status = self.poll_minion(kill_minion)
            if not any(minion_status):
                safe_to_shutdown = True

class CanvasModule(BaseMinion):
    def __init__(self, *args, **kwargs):
        super(CanvasModule, self).__init__(*args, **kwargs)
        self._win = None

    def main(self):
        try:
            APP = app.Application(backend_name='pyqt5')
            APP.create()
            self._win = GLDisplay(self)
            self._win.controllerProcName = 'GUI'
            self._win.show()
            self.info('Starting display window')
            APP.run()
            self._win.on_close()
            APP.quit()
        except Exception as e:
            self.error(e)