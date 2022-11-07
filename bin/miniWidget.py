'''
This file contains multiple wrapper classes for dynamic adding and altering GUI components
'''

import PyQt5.QtWidgets as qw
import PyQt5.QtCore as qc

from minion import BaseMinion

import traceback, sys
from importlib import util, reload


class BaseQtWindow(qw.QMainWindow):
    '''
    A wrapper class of QMainWindow which should define the basic layout
    of a classic minipoly GUI window
    '''

    def __int__(self):
        super().__init__()

        self._windowSize = (0, 0)
        self._windowTitle = None
        self._menuBar = self.menuBar()
        self._centralWidget = qw.QWidget()
        self.setCentralWidget(self._centralWidget)

    @property
    def window_title(self):
        return self._windowTitle

    @window_title.setter
    def window_title(self, value):
        self._windowTitle = value
        if self._windowTitle is not None:
            self.setWindowTitle(self._windowTitle)

    @property
    def window_size(self):
        return self._windowSize

    @window_size.setter
    def window_size(self, value):
        self._windowSize = value
        self.resize(*self._windowSize)
