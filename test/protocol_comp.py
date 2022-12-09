import traceback

import numpy as np
import vispy

from bin.app import AbstractGUIModule
from bin.minion import BaseMinion, AbstractMinionMixin, LoggerMinion, TimerMinion
import pandas as pd
from vispy import gloo, app
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
                # print(f"{(cur_time-self.model._data['time'][row_idx])*1000}")
                self._processHandler.set_state_to('OPENGL','u_radius',self.model._data['u_radius'][row_idx])
        except:
            print(traceback.format_exc())
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

# class TestCompiler(TimerMinion):
#
#     def initialize(self):
#         self._mainfunc = ProtocolCompiler(self)
#         self.on_time = self._mainfunc.on_time

class CanvasModule(BaseMinion):
    def __init__(self, *args, **kwargs):
        super(CanvasModule, self).__init__(*args, **kwargs)
        self._win = None

    def main(self):
        try:
            vispy.use('glfw')
            self._win = GraphicProtocolCompiler(self)
            self._win.initialize()
            self._win.show()
            self.info('Starting display window')
            app.run()
            self._win.on_close()
        except Exception as e:
            self.error(e)

class GraphicProtocolCompiler(app.Canvas, AbstractMinionMixin):

    def __init__(self, processHandler: BaseMinion = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        app.Canvas.__init__(self, *args, **kwargs)
        self.timer = app.Timer('auto', self.on_timer, start=True)

        self._processHandler = processHandler
        self._setTime = 0
        self._tic = 0
        self._rmtShutdown = False
        self._shared_uniforms = None
        self.VS = """
            #version 130
            attribute vec2 a_pos;
            varying vec2 v_pos;
            void main () {
                v_pos = a_pos;
                gl_Position = vec4(a_pos, 0.0, 1.0);
            }
            """

        # Define Fragment shader
        self.FS = """
            varying vec2 v_pos; 
            uniform vec2 u_resolution; 
            uniform float u_radius; 
            void main() {
                vec2 st = v_pos.yx;
                st.x *= u_resolution.y/u_resolution.x;
                vec3 color = vec3(step(length(st),u_radius));
                gl_FragColor = vec4(color,1.);
            }
        """
        self.program = None

    def initialize(self):
        self.program = gloo.Program(self.VS, self.FS)
        self.program['a_pos'] = np.array([[-1., -1.], [-1., 1.], [1., -1.], [1., 1.]], np.float32)  # /2.
        self.program['u_time'] = 0
        self.program['u_alpha'] = np.float32(1)
        gloo.set_state("translucent")
        self.program['u_resolution'] = (self.size[0], self.size[1])

        self._processHandler.create_state('u_radius',0)
        self.program['u_radius'] = self._processHandler.get_state_from(self._processHandler.name,'u_radius')

    def on_timer(self, event):

        if self.timer.elapsed - self._setTime > .01:  # Limit the call frequency to 1 second

            # self._processHandler.set_state_to(self._processHandler.name, 'u_radius', np.sin(self.timer.elapsed))
            # Check if any remote calls have been set first before further processing
            if self._processHandler.status == -1:
                self._rmtShutdown = True
                self.on_close()
            elif self._processHandler.status == 0:
                self.on_close()

            self._setTime = np.floor(self.timer.elapsed)
        self.update()


    def on_draw(self, event):
        # Define the update rule
        gloo.clear([0,0,0,0])
        self.program['u_radius'] = self._processHandler.get_state_from(self._processHandler.name,'u_radius')
        self.program.draw('triangle_strip')

    def on_resize(self, event):
        # Define how should be rendered image should be resized by changing window size
        gloo.set_viewport(0, 0, *self.physical_size)
        self.program['u_resolution'] = (self.size[0],self.size[1])

    def on_close(self):
        if not self._rmtShutdown:
            self._processHandler.set_state_to(self._processHandler.name, 'status', -1)
        self.close()


if __name__ == '__main__':
    GUI = TestGUI('testgui')
    GL_canvas = CanvasModule('OPENGL')
    GL_canvas.connect(GUI)
    logger = LoggerMinion('TestGUI logger')
    GUI.attach_logger(logger)
    GL_canvas.attach_logger(logger)
    logger.run()
    GUI.run()
    GL_canvas.run()