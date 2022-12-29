import numpy as np
from bin.gui import DataframeTable
from bin.compiler import QtCompiler, GLCompiler
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
        self.addTableBox('Protocol')
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
        self.startTimer()
        self.start_timing('protocol_timer')
        self._timer_started = True
        self.timer_switcher.setText('Stop')

    def startTimer(self):
        self.set_state('is_running', True)

    def _stopTimer(self):
        self.stopTimer()
        self.stop_timing('protocol_timer')
        self._timer_started = False  # self._time = self._time.elapsed()
        self.timer_switcher.setText('Start')

    def stopTimer(self):
        self.set_state('is_running', False)

    def on_protocol(self, t):
        cur_time = t
        if self.tables['Protocol'].model():
            data = self.tables['Protocol'].model()._data
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
                        self.tables['Protocol'].selectRow(row_idx)
                        for k in data.keys():
                            if k in self.get_shared_state_names('OPENGL'):
                                self.set_state_to('OPENGL',k,float(data[k][row_idx]))


    def _init_menu(self):
        self._menubar = self.menuBar()
        self._menu_file = self._menubar.addMenu('File')
        Load = qw.QAction("Load shader", self)
        Load.setShortcut("Ctrl+O")
        Load.setStatusTip("Load fragment shader")
        Load.triggered.connect(self.load_shader)
        self._menu_file.addAction(Load)
        Exit = qw.QAction("Quit", self)
        Exit.setShortcut("Ctrl+Q")
        Exit.setStatusTip("Exit program")
        Exit.triggered.connect(self.close)
        self._menu_file.addAction(Exit)

    def load_shader(self):
        rendererScriptName = qw.QFileDialog.getOpenFileName(self, 'Open File', './renderer',
                                                            "GLSL shader (*.FS *.glsl)", "",
                                                            qw.QFileDialog.DontUseNativeDialog)
        self.send('OPENGL', 'load_shader', rendererScriptName[0])



class GraphicProtocolCompiler(GLCompiler):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def on_init(self):
        gloo.set_state("translucent")
        self.program['a_pos'] = np.array([[-1., -1.], [-1., 1.], [1., -1.], [1., 1.]], np.float32)  # /2.
        self.program['u_time'] = 0
        self.program['u_resolution'] = (self.size[0], self.size[1])

    def parse_msg(self, msg_type, msg):
        if msg_type == 'load_shader':
            for i in self._shared_uniform_states:
                self.remove_state(i)
            self._shared_uniform_states = []
            self.info(f"Loading fragment shader from:{msg}")
            self.load_FS(msg)
            self.program = gloo.Program(self.VS, self.FS)
            self.initialize()

    def on_timer(self, event):
        self.get('GUI')
        is_running = self.get_state_from('GUI', 'is_running')
        if not self.is_protocol_running():
            if is_running:
                self.run_protocol()
        else:
            if not is_running:
                self.stop_protocol()

    def on_protocol(self, event, offset):
        self.program['u_time'] = event.elapsed
        self.update_shared_uniform()
        self.update()

    def update_shared_uniform(self):
        for i in self._shared_uniform_states:
            self.program[i] = self.get_state(i)

    def on_draw(self, event):
        # Define the update rule
        gloo.clear('black')
        if self.is_protocol_running():
            self.program.draw('triangle_strip')
