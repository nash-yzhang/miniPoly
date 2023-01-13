from bin.app import AbstractGUIAPP, AbstractGLAPP
from compiler import ServoProtocolCommander

class ServoCompilerGUI(AbstractGUIAPP):

    def initialize(self):
        super().initialize()
        self._win = ServoProtocolCommander(self)
        self.info("Starting GUI")
        self._win.show()
