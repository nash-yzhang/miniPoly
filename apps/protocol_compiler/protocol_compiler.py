import pandas as pd
from time import time
import numpy as np

import PyQt5.QtWidgets as qw
import PyQt5.QtCore as qc
import sys

from bin.minion import BaseMinion, AbstractMinionMixin
import sys

import PyQt5.QtWidgets as qw
import PyQt5.QtCore as qc
import pandas as pd


class ProtocolCommander(qw.QMainWindow):
    def __init__(self, processHandler: BaseMinion = None, windowSize=(400, 400), refresh_rate=200):
        super().__init__()
        self._processHandler = processHandler
        self._name = self._processHandler.name
        self._windowSize = windowSize
        self.setWindowTitle(self._name)
        self.resize(*self._windowSize)

        self._timer = qc.QTimer()
        self._timer.timeout.connect(self.on_time)
        self._time = qc.QTime()
        self._timer.setInterval(int(1000/refresh_rate))
        self._timer_started = False

        self.table = qw.QTableView()
        self.model = DataframeModel(data=None)
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

    def switch_timer(self):
        if self._timer_started:
            self._timer.stop()
            self._timer_started = False # self._time = self._time.elapsed()
            self.timer_switcher.setText('Start')
        else:
            self._timer_started = True
            self._time.restart()
            self._timer.start()
            self.timer_switcher.setText('Stop')

    def on_time(self):
        try:
            row_idx = next(i for i, v in enumerate(self.model._data['time']) if v > self._time.elapsed()/1000)
            self.table.selectRow(row_idx)
        except:
            self.table.clearSelection()

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

class ProtocolCommander(qw.QMainWindow, AbstractMinionMixin):

    def add_protocol(self, minion_name: str, protocol: [dict, pd.DataFrame]):
        '''
        :param minion_name: protocol_compiler name
        :param protocol: a dictionary or pandas dataframe whose index column should be named 'cmd_time'
                         and the other columns correspond to the parameters registered.
        :return:
        '''
        self.link_minion(minion_name)

        if type(protocol) == dict:
            protocol = pd.DataFrame(protocol)
            protocol = protocol.set_index('cmd_time')
            protocol = protocol.sort_index()

        self.protocols[minion_name] = protocol

    def on_time(self):
        print(qc.QTime.currentTime())