import os.path
import sys
import traceback
import pandas as pd
from time import perf_counter

import PyQt5.QtWidgets as qw
import PyQt5.QtCore as qc
from pysinewave import SineWave


class ProtocolCommander(qw.QMainWindow):
    def __init__(self, windowSize=(400, 400), refresh_rate=1000):
        super().__init__()
        self._name = 'test'
        self._windowSize = windowSize
        self.setWindowTitle(self._name)
        self.resize(*self._windowSize)

        self._timer = qc.QTimer()
        self._timer.timeout.connect(self.on_time)
        self._init_time = -1
        self._elapsed = 0
        self._timerInterval = int(1000 / refresh_rate)
        self._timer.setInterval(self._timerInterval)
        self._timer_started = False

        self.frames = {}
        self.tables = {}
        self.addTableBox('Audio')
        self.addTableBox('Visual')

        self.layout = qw.QVBoxLayout()
        self.groupbox_layout = qw.QHBoxLayout()
        for val in self.frames.values():
            self.groupbox_layout.addWidget(val)
        self.layout.addLayout(self.groupbox_layout)

        self.timer_switcher = qw.QPushButton('Start')
        self.timer_switcher.clicked.connect(self.switch_timer)
        self.layout.addWidget(self.timer_switcher)

        self.main_widget = qw.QWidget()
        self.main_widget.setLayout(self.layout)
        self.setCentralWidget(self.main_widget)

        self.row_idx = -1
        self.sinewave = None
        self.sinewave_played = False

        self.protocol_params = {}
        self.protocols = {}

    def addTableBox(self, name):
        frame = qw.QGroupBox(self)
        frame.setTitle(name)
        table = DataframeTable(self.centralWidget())
        frame_layout = qw.QVBoxLayout()
        frame_layout.addWidget(table)
        frame.setLayout(frame_layout)
        self.frames[name] = frame
        self.tables[name] = table

    @property
    def elapsed(self):
        self._elapsed = perf_counter() - self._init_time
        return self._elapsed

    def switch_timer(self):
        if self._timer_started:
            self._stopTimer()
        else:
            self._startTimer()

    def _startTimer(self):
        data = self.tables['Audio'].model()._data
        self.sinewave = SineWave(pitch=data['p_freq'][0],
                                 pitch_per_second=2000,
                                 decibels_per_second=2000)
        self.sinewave.play()
        self._timer_started = True
        self._init_time = perf_counter()
        self._timer.start()
        self.timer_switcher.setText('Stop')

    def _stopTimer(self):
        self.sinewave.stop()
        self._timer.stop()
        self._timer_started = False  # self._time = self._time.elapsed()
        self.timer_switcher.setText('Start')

    def on_time(self):
        cur_time = self.elapsed
        # can_stop = [False,False]
        can_stop = [False]

        try:
            data = self.tables['Audio'].model()._data
            time_col = data['time']
            if cur_time <= (time_col.max() + self._timerInterval):
                row_idx = None
                for i,v in enumerate(time_col):
                    if v >= cur_time:
                        row_idx = i-1
                        break
                if row_idx is None:
                    self._stopTimer()
                else:
                    if row_idx != self.row_idx:
                        pitch = data['p_freq'][row_idx]
                        self.sinewave.set_pitch(pitch)
                        if pitch == 0:
                            self.sinewave.set_volume(-1000)
                        else:
                            self.sinewave.set_volume(0)
                        self.tables['Audio'].selectRow(row_idx)
                        self.row_idx = row_idx
            else:
                self._stopTimer()
        except:
            print(traceback.format_exc())
            self.tables['Audio'].clearSelection()

        # try:
        #     time_col = self.table2.model()._data['time']
        #     if cur_time <= (time_col.max()+self._timer.interval()):
        #         row_idx = next(i-1 for i, v in enumerate(time_col) if v >= cur_time)
        #         self.table2.selectRow(row_idx)
        #     else:
        #         can_stop[1] = True
        # except:
        #     print(traceback.format_exc())
        #     self.table2.clearSelection()
        if all(can_stop):
            self._stopTimer()

    def _init_menu(self):
        self._menubar = self.menuBar()
        self._menu_file = self._menubar.addMenu('File')
        # loadfile = qw.QAction("Load", self)
        # loadfile.setShortcut("Ctrl+O")
        # loadfile.setStatusTip("Load data from Excel/h5 file")
        # loadfile.triggered.connect(self.loadfile)
        Exit = qw.QAction("Quit", self)
        Exit.setShortcut("Ctrl+Q")
        Exit.setStatusTip("Exit program")
        Exit.triggered.connect(self.close)
        # self._menu_file.addAction(loadfile)
        self._menu_file.addAction(Exit)

    # def loadfile(self):
    #     datafile = qw.QFileDialog.getOpenFileName(self, 'Open File',
    #                                               'D:\\Yue Zhang\\OneDrive\\Bonhoeffer Lab\\PycharmProjects\\miniPoly\\apps\\protocol_compiler',
    #                                               "Data file (*.xls *.xlsx *.h5)", "",
    #                                               qw.QFileDialog.DontUseNativeDialog)
    #     if datafile[0]:
    #         self.table1.loadfile(datafile[0])
    #         self.main_widget.update()


class DataframeTable(qw.QTableView):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls:
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls:
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        if event.mimeData().hasUrls:
            url = event.mimeData().urls()[0].path()[1:]
            if os.path.isfile(url):
                self.loadfile(url)
        else:
            event.ignore()

    def loadfile(self, fdir):
        if os.path.splitext(fdir)[1] in ['.xls', '.xlsx', '.h5']:
            self.setModel(DataframeModel(data=pd.read_excel(fdir)))


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


def main():
    app = qw.QApplication(sys.argv)
    ex = ProtocolCommander()
    ex.show()
    app.exec_()


if __name__ == '__main__':
    main()
