import numpy as np

from PyQt5 import QtGui
import PyQt5.QtWidgets as qw
import PyQt5.QtGui as qg

import pyqtgraph as pg

from bin.compiler import QtCompiler, AbstractCompiler
import pyfirmata as pf

from bin.widgets.prototypes import AbstractGUIAPP, AbstractAPP
from bin.minion import LoggerMinion as Logger

class BaseApp(AbstractAPP):

    def __init__(self, name, compiler, refresh_interval=None, **kwargs):
        super(BaseApp, self).__init__(name, refresh_interval=refresh_interval)
        self._compiler_func = compiler
        self._compiler_kwargs = kwargs

    def initialize(self):
        super().initialize()
        if self._compiler_kwargs:
            self._compiler = self._compiler_func(self, **self._compiler_kwargs)
        else:
            self._compiler = self._compiler_func(self)
        self.info(f"[{self.name}] Initialized")

class StandardGUIAPP(BaseApp):

    def __init__(self, *args, **kwargs):
        super(StandardGUIAPP, self).__init__(*args,**kwargs)
    def initialize(self):
        super().initialize()
        self._compiler.show()

class ArduinoHandler(AbstractCompiler):

    def __init__(self, *args, **kwargs):
        super(ArduinoHandler, self).__init__(*args, **kwargs)
        self._registered_pins = {}
        self._device = None
        self.create_state('COM', -1) # Listen to the change of this state to connect to the device
        self.watch_state('COM', -1)
        self.create_state('PIN', [])

    def open_device(self, COM_PORT):
        try:
            self._device = pf.Arduino(f"COM{COM_PORT}")
        except Exception as e:
            self.error(e)
            return False

    def close_device(self):
        if self._device is not None:
            self._device.exit()
            self._device = None

    def register_pin(self, pin):
        if pin in self._registered_pins:
            self.error(f"Pin '{pin}' is already registered")
            return False
        else:
            self._registered_pins[pin] = self._device.get_pin(pin)
            self.create_state(f'PIN_{pin}', 0)
            return True

    def unregister_pin(self, pin):
        if pin in self._registered_pins:
            del self._registered_pins[pin]
            self.remove_state(f'PIN_{pin}')
            return True
        else:
            self.error(f"Pin '{pin}' is not registered")
            return False

    def on_time(self, t):
        COM_port = self.get_state('COM')
        if self.watch_state('COM',COM_port) and self._device is None:
            self.open_device(COM_port)



class StandardGUICompiler(QtCompiler):

    def __init__(self, processHandler):
        super(StandardGUICompiler,self).__init__(processHandler)
        self._init_ui()

    def _init_ui(self):
        self._menu_bar = self.menuBar()
        self._menu_file = self._menu_bar.addMenu('File')

        Exit = qw.QAction("Quit", self)
        Exit.setShortcut("Ctrl+Q")
        Exit.setStatusTip("Exit program")
        Exit.triggered.connect(self.close)

        self._menu_file.addAction(Exit)

        self.init_ui()

    def init_ui(self):
        pass

