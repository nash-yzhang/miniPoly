import os.path
import sys
import traceback
import pandas as pd
from time import perf_counter

import PyQt5.QtWidgets as qw
import PyQt5.QtCore as qc


class ProtocolCommander(qw.QMainWindow):
    def __init__(self, windowSize=(400, 400), refresh_rate=200):
        super().__init__()
        self._name = 'test'
        self._windowSize = windowSize
        self.setWindowTitle(self._name)
        self.resize(*self._windowSize)

        self._timer = qc.QTimer()
        self._timer.timeout.connect(self.on_time)
        self._init_time = -1
        self._elapsed = 0
        self._timer.setInterval(int(1000/refresh_rate))
        self._timer_started = False

        self.table = DataframeTable(self.centralWidget())
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
            row_idx = next(i-1 for i, v in enumerate(self.table.model()._data['time']) if v > cur_time)
            self.table.selectRow(row_idx)
        except:
            print(traceback.format_exc())
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
        datafile = qw.QFileDialog.getOpenFileName(self, 'Open File',
                                                  'D:\\Yue Zhang\\OneDrive\\Bonhoeffer Lab\\PycharmProjects\\miniPoly\\apps\\protocol_compiler',
                                                  "Data file (*.xls *.xlsx *.h5)", "",
                                                  qw.QFileDialog.DontUseNativeDialog)
        if datafile[0]:
            self.table.loadfile(datafile[0])
            # self.model = DataframeModel(data=pd.read_excel(datafile[0]))
            # self.table.setModel(self.model)
            self.main_widget.update()


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

    def loadfile(self,fdir):
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