import traceback
from time import perf_counter
import numpy as np
from bin.widgets.prototypes import AbstractGUIAPP, AbstractGLAPP
from bin.gui import DataframeTable
from bin.minion import LoggerMinion
from bin.compiler.graphics import QtCompiler, GLCompiler
import PyQt5.QtWidgets as qw
from vispy import gloo


class ProtocolCommander(QtCompiler):
    def __init__(self, *args, windowSize=(900, 300), **kwargs):
        super().__init__(*args, **kwargs)
        self.add_timer('protocol_timer', self.on_protocol)
        self.create_state('is_running', False)

        self._timer_started = False
        self.timer_switcher = qw.QPushButton('Start')
        self.timer_switcher.clicked.connect(self.switch_timer)
        self.resize(*windowSize)

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

        self.sinewave = None

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
        self.startTimer()
        self.start_timing('protocol_timer')
        self._timer_started = True
        self.timer_switcher.setText('Stop')

    def startTimer(self):
        self.set_state('is_running', True)
        self.set_state_to('OPENGL', 'u_radius', 0)

    def _stopTimer(self):
        self.stopTimer()
        self.stop_timing('protocol_timer')
        self._timer_started = False  # self._time = self._time.elapsed()
        self.timer_switcher.setText('Start')

    def stopTimer(self):
        self.set_state('is_running', False)
        self.set_state_to('OPENGL', 'u_radius', 0)

    def on_protocol(self, t):
        cur_time = t
        try:
            data = self.tables['Visual'].model()._data
            time_col = data['time']
            if cur_time <= (time_col.max() + self.timerInterval()):
                row_idx = None
                for i, v in enumerate(time_col):
                    if v >= cur_time:
                        row_idx = i - 1
                        break
                if row_idx is None:
                    self._stopTimer()
                else:
                    if self.watch_state('visual_row', row_idx):
                        self.tables['Visual'].selectRow(row_idx)
                        u_radius = data['u_radius'][row_idx].astype(float)
                        while True:
                            try:
                                self.set_state_to('OPENGL', 'u_radius', u_radius)
                                break
                            except:
                                pass
                        print(f'CMD: {perf_counter()}')


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


class GraphicProtocolCompiler(GLCompiler):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def on_init(self):
        self.program['a_pos'] = np.array([[-1., -1.], [-1., 1.], [1., -1.], [1., 1.]], np.float32)  # /2.
        self.program['u_time'] = 0
        self.program['u_radius'] = 0.

        gloo.set_state("translucent")
        self.program['u_resolution'] = (self.size[0], self.size[1])

    def on_timer(self, event):
        if not self.is_protocol_running():
            is_running = self.get_state_from('testgui', 'is_running')
            if is_running:
                self.run_protocol()

    def on_protocol(self, event, offset):
        u_radius = self.get_state('u_radius')
        if self.watch_state('u_radius',u_radius):
            self.program['u_radius'] = u_radius
            print(f'GL: {perf_counter()}')

        self.update()

    def on_draw(self, event):
        # Define the update rule
        gloo.clear('black')
        if self.is_protocol_running():
            self.program.draw('triangle_strip')


class TestGUI(AbstractGUIAPP):

    def initialize(self):
        super().initialize()
        self._win = ProtocolCommander(self)
        self.info("Starting GUI")
        self._win.show()


class CanvasModule(AbstractGLAPP):

    def initialize(self):
        super().initialize()
        self._win = GraphicProtocolCompiler(self, app=self._app, refresh_interval=1,
                                            VS='../apps/protocol_compiler/default.VS',
                                            FS='../apps/protocol_compiler/default.FS')
        self.info('Starting display window')
        self._win.initialize()
        self._win.show()


if __name__ == '__main__':
    GUI = TestGUI('testgui',interval=1)
    GL_canvas = CanvasModule('OPENGL',interval=1)
    GL_canvas.connect(GUI)
    logger = LoggerMinion('TestGUI logger')
    GUI.attach_logger(logger)
    GL_canvas.attach_logger(logger)
    logger.run()
    GL_canvas.run()
    GUI.run()
