from bin.app import AbstractGUIModule
from bin.minion import BaseMinion, AbstractMinionMixin, LoggerMinion, TimerMinion
import pandas as pd
import numpy as np
import sys
from time import perf_counter

import PyQt5.QtWidgets as qw
import PyQt5.QtCore as qc

class TestGUI(AbstractGUIModule):

    def gui_init(self):
        self._win = ProtocolCommander(self)

class ProtocolCommander(qw.QMainWindow, AbstractMinionMixin):
    def __init__(self, processHandler: BaseMinion = None, windowSize=(400, 400), refresh_rate=200):
        super().__init__()
        self._processHandler = processHandler
        self._name = self._processHandler.name
        self._windowSize = windowSize
        self.setWindowTitle(self._name)
        self.resize(*self._windowSize)

        self._timer = qc.QTimer()
        self._timer.timeout.connect(self.on_time)
        self._init_time = -1
        self._elapsed = 0
        self._timer.setInterval(int(1000/refresh_rate))
        self._timer_started = False

        self.table = qw.QTableView()
        self.model = DataframeModel(data=pd.DataFrame({}))
        self.table.setModel(self.model)
        self.timer_switcher = qw.QPushButton('Start')
        self.timer_switcher.clicked.connect(self.switch_timer)
        self.layout = qw.QVBoxLayout()
        self.layout.addWidget(self.table)
        self.layout.addWidget(self.timer_switcher)

        self.main_widget = qw.QWidget()
        self.main_widget.setLayout(self.layout)
        self.setCentralWidget(self.main_widget)

        self.protocol_params = {}
        self.protocols = {}

        self._watching_state = {}

        self._init_menu()

    @property
    def elapsed(self):
        self._elapsed = perf_counter()-self._init_time
        return self._elapsed

    def switch_timer(self):
        if self._timer_started:
            self._timer.stop()
            self._timer_started = False # self._time = self._time.elapsed()
            self.timer_switcher.setText('Start')
        else:
            self._timer_started = True
            self._init_time = perf_counter()
            self._timer.start()
            self.timer_switcher.setText('Stop')

    def on_time(self):
        try:
            cur_time = self.elapsed
            row_idx = next(i-1 for i, v in enumerate(self.model._data['time']) if v > cur_time)
            if self.watch_state('row_idx',row_idx):
                self.table.selectRow(row_idx)
                print(f"{(cur_time-self.model._data['time'][row_idx])*1000}")
        except:
            self.table.clearSelection()

    def watch_state(self,name,val):
        if name not in self._watching_state.keys():
            self._watching_state[name] = val
            return True
        else:
            changed = val != self._watching_state[name]
            self._watching_state[name] = val
            return changed



    def _init_menu(self):
        self._menubar = self.menuBar()
        self._menu_file = self._menubar.addMenu('File')
        loadfile = qw.QAction("Load", self)
        loadfile.setShortcut("Ctrl+O")
        loadfile.setStatusTip("Load data from Excel/h5 file")
        loadfile.triggered.connect(self.loadfile)
        Exit = qw.QAction("Quit", self)
        Exit.setShortcut("Ctrl+Q")
        Exit.setStatusTip("Exit program")
        Exit.triggered.connect(self.close)
        self._menu_file.addAction(loadfile)
        self._menu_file.addAction(Exit)

    def loadfile(self):
        datafile = qw.QFileDialog.getOpenFileName(self, 'Open File', 'D:\\Yue Zhang\\OneDrive\\Bonhoeffer Lab\\PycharmProjects\\miniPoly\\apps\\protocol_compiler',
                                                  "Data file (*.xls *.xlsx *.h5)", "",
                                                  qw.QFileDialog.DontUseNativeDialog)
        if datafile[0]:
            self.model = DataframeModel(data=pd.read_excel(datafile[0]))
            self.table.setModel(self.model)
            self.main_widget.update()

class DataframeModel(qc.QAbstractTableModel):
    def __init__(self, data, parent=None):
        qc.QAbstractTableModel.__init__(self, parent)
        self._data = data

    def rowCount(self, parent=None):
        return len(self._data.values)

    def columnCount(self, parent=None):
        return self._data.columns.size

    def data(self, index, role=qc.Qt.DisplayRole):
        if index.isValid():
            if role == qc.Qt.DisplayRole:
                return str(self._data.iloc[index.row()][index.column()])
        return None

    def headerData(self, col, orientation, role):
        if orientation == qc.Qt.Horizontal and role == qc.Qt.DisplayRole:
            return self._data.columns[col]
        return None

class TestCompiler(TimerMinion):

    def initialize(self):
        self._mainfunc = ProtocolCompiler(self)
        self.on_time = self._mainfunc.on_time


class ProtocolCompiler(AbstractMinionMixin):

    def __init__(self,processHandler: BaseMinion=None):
        super().__init__()
        self._processHandler = processHandler
        self._name = self._processHandler.name

    def on_time(self):
        self._processHandler.info('Testing')


if __name__ == '__main__':
    # GUI = TestGUI('testgui')
    GUI = TestCompiler('test')
    logger = LoggerMinion('TestGUI logger')
    GUI.attach_logger(logger)
    logger.run()
    GUI.run()