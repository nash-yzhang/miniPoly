import traceback

from miniPoly.util.gui import DataframeTable
from miniPoly.compiler.graphics import QtCompiler
from miniPoly.prototype.Logging import LoggerMinion
from miniPoly.prototype.GUI import AbstractGUIAPP
import PyQt5.QtWidgets as qw
from time import sleep


class TestApp(AbstractGUIAPP):

    def initialize(self):
        super().initialize()
        self._compiler = ProtocolCommander(self)
        self._compiler.show()

class ProtocolCommander(QtCompiler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_timer('protocol_timer',self.on_protocol)
        self.create_state('is_running',False)

        self._timer_started = False
        self.timer_switcher = qw.QPushButton('Start')
        self.timer_switcher.clicked.connect(self.switch_timer)

        self.frames = {}
        self.tables = {}
        self.addTableBox('Visual')
        self.groupbox_layout = qw.QHBoxLayout()
        for val in self.frames.values():
            self.groupbox_layout.addWidget(val)

        self.layout = qw.QVBoxLayout()
        self.layout.addLayout(self.groupbox_layout)
        self.layout.addWidget(self.timer_switcher)

        self.main_widget = qw.QWidget()
        self.main_widget.setLayout(self.layout)
        self.setCentralWidget(self.main_widget)

        self._init_menu()

    def addTableBox(self, name):
        frame = qw.QGroupBox(self)
        frame.setTitle(name)
        table = DataframeTable(self.centralWidget())
        frame_layout = qw.QVBoxLayout()
        frame_layout.addWidget(table)
        frame.setLayout(frame_layout)
        self.frames[name] = frame
        self.tables[name] = table

    def switch_timer(self):
        if self._timer_started:
            self._stopTimer()
        else:
            self._startTimer()

    def _startTimer(self):
        self.start_timing('protocol_timer')
        self._timer_started = True
        self.timer_switcher.setText('Stop')

    def startTimer(self):
        self.set_state('is_running',True)

    def _stopTimer(self):
        self.stop_timing('protocol_timer')
        self._timer_started = False  # self._time = self._time.elapsed()
        self.timer_switcher.setText('Start')

    def stopTimer(self):
        self.set_state('is_running',False)
        sleep(.1)

    def on_protocol(self,t):
        cur_time = t
        try:
            data = self.tables['Visual'].model()._data
            time_col = data['time']
            if cur_time <= (time_col.max() + self.timerInterval()):
                row_idx = None
                for i,v in enumerate(time_col):
                    if v >= cur_time:
                        row_idx = i-1
                        break
                if row_idx is None:
                    self._stopTimer()
                else:
                    if self.watch_state('visual_row',row_idx):
                        self.tables['Visual'].selectRow(row_idx)

        except:
            print(traceback.format_exc())
            for i in self.tables:
                i.clearSelection()

    def _init_menu(self):
        self._menubar = self.menuBar()
        self._menu_file = self._menubar.addMenu('File')
        Exit = qw.QAction("Quit", self)
        Exit.setShortcut("Ctrl+Q")
        Exit.setStatusTip("Exit program")
        Exit.triggered.connect(self.close)
        self._menu_file.addAction(Exit)

    def close(self) -> None:
        pass


if __name__ == '__main__':
    app = TestApp('testgui')
    logger = LoggerMinion('TestApp logger')
    app.attach_logger(logger)
    logger.run()
    app.run()