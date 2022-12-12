import os
import traceback

import numpy as np
import vispy
from pysinewave import SineWave

from bin.app import AbstractGUIModule
from bin.minion import BaseMinion, AbstractMinionMixin, LoggerMinion, TimerMinion
import pandas as pd
from vispy import gloo, app
from time import perf_counter

import PyQt5.QtWidgets as qw
import PyQt5.QtCore as qc
from multiprocessing import Lock

class TestGUI(AbstractGUIModule):

    def gui_init(self):
        self._win = ProtocolCommander(self)

class ProtocolCommander(qw.QMainWindow, AbstractMinionMixin):
    def __init__(self, processHandler: BaseMinion = None, windowSize=(400, 400), refresh_interval=10):
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
        self._refreshInterval = refresh_interval
        self._timer.setInterval(refresh_interval)
        self._timer_started = False

        self.timer_switcher = qw.QPushButton('Start')
        self.timer_switcher.clicked.connect(self.switch_timer)

        self.frames = {}
        self.tables = {}
        self.addTableBox('Audio')
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

        self.protocol_params = {}
        self.protocols = {}

        self._watching_state = {}

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

    @property
    def elapsed(self):
        self._elapsed = perf_counter()-self._init_time
        return self._elapsed

    def switch_timer(self):
        if self._timer_started:
            self._stopTimer()
        else:
            self._startTimer()

    def _startTimer(self):
        self.startTimer()
        self._timer_started = True
        self._init_time = perf_counter()
        self._timer.start()
        self.timer_switcher.setText('Stop')

    def startTimer(self):
        data = self.tables['Audio'].model()._data
        self.sinewave = SineWave(pitch=data['p_freq'][0],
                                 pitch_per_second=2000,
                                 decibels_per_second=2000)
        self.sinewave.play()
        # pass

    def _stopTimer(self):
        self.stopTimer()
        self._timer.stop()
        self._timer_started = False  # self._time = self._time.elapsed()
        self.timer_switcher.setText('Start')

    def stopTimer(self):
        self.sinewave.stop()
        self._processHandler.set_state_to('OPENGL','u_rot_speed',0)
        # pass

    def on_time(self):
        cur_time = self.elapsed
        try:
            data = self.tables['Visual'].model()._data
            time_col = data['time']
            if cur_time <= (time_col.max() + self._refreshInterval):
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
                        p_time = data['time'][row_idx].astype(float)
                        u_rot_speed = data['u_rot_speed'][row_idx].astype(float)
                        while True:
                            try:
                                self._processHandler.set_state_to('OPENGL','p_time',p_time)
                                self._processHandler.set_state_to('OPENGL','u_rot_speed',u_rot_speed)
                                break
                            except:
                                pass

        except:
            print(traceback.format_exc())
            for i in self.tables:
                i.clearSelection()

        try:
            data = self.tables['Audio'].model()._data
            time_col = data['time']
            if cur_time <= (time_col.max() + self._refreshInterval):
                row_idx = None
                for i,v in enumerate(time_col):
                    if v >= cur_time:
                        row_idx = i-1
                        break
                if row_idx is None:
                    self._stopTimer()
                else:
                    if self.watch_state('visual_row',row_idx):
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
    #     datafile = qw.QFileDialog.getOpenFileName(self, 'Open File', 'D:\\Yue Zhang\\OneDrive\\Bonhoeffer Lab\\PycharmProjects\\miniPoly\\apps\\protocol_compiler',
    #                                               "Data file (*.xls *.xlsx *.h5)", "",
    #                                               qw.QFileDialog.DontUseNativeDialog)
    #     if datafile[0]:
    #         self.model = DataframeModel(data=pd.read_excel(datafile[0]))
    #         self.table.setModel(self.model)
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
        self.timer = app.Timer(.01, self.on_timer, start=True)

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
            uniform float u_time;
            uniform float u_rot_speed;
            uniform float u_offset_angle;
            
            vec2 rotate(vec2 st, float angle) {
                 mat2 rotationMatrix = mat2(cos(angle), -sin(angle), sin(angle), cos(angle)); // identity matrix
                 return rotationMatrix * st;
            }

            vec2 rotate_around(vec2 st, vec2 cen, float angle) {
                return rotate(st-cen,angle);
            }

            float rectangle(vec2 st, vec2 cen, float width, float height) {
                st -= cen;
                return step(0.,st.x) * step(st.x,width) * step(0., st.y) * step(st.y,height);
            }

            float rot_rectangle(vec2 st, vec2 rec_cen, float width, float height, float rot_ang, vec2 rot_cen) {
                vec2 new_st = rotate_around(st,rot_cen,rot_ang)-rec_cen;
                return rectangle(new_st, rec_cen, width, height);
            }
            
            # define PI 3.141592653 
            void main() {
                vec2 st = v_pos/2+.5;
                st.x *= u_resolution.x/u_resolution.y;
                
                float width = .05;
                float height = .4;
                vec2 rec_cen = vec2(-width/4.,.1);
                
                float red_rot_ang = -(u_time*u_rot_speed/8.+1.+u_offset_angle/180)*PI/6.;
                vec2 red_rot_cen = vec2(0.100,0.30);
                float red_saber = rot_rectangle(st, rec_cen, width, height,red_rot_ang,red_rot_cen);
                
                float blue_rot_ang = (u_time*u_rot_speed/8.+1.+u_offset_angle/180)*PI/6.;
                vec2 blue_rot_cen = vec2(0.850,0.30);
                float blue_saber = rot_rectangle(st, rec_cen, width, height,blue_rot_ang,blue_rot_cen);
                
                vec3 color = vec3(red_saber,0.,blue_saber);
                gl_FragColor = vec4(red_saber,0.,blue_saber,1.0);                
            }
        """
        self.program = None

    def initialize(self):
        self.program = gloo.Program(self.VS, self.FS)
        self.program['a_pos'] = np.array([[-1., -1.], [-1., 1.], [1., -1.], [1., 1.]], np.float32)  # /2.
        self.program['u_time'] = 0
        self.program['u_offset_angle'] = 0.

        self.program['u_alpha'] = np.float32(1)
        gloo.set_state("translucent")
        self.program['u_resolution'] = (self.size[0], self.size[1])

        self._processHandler.create_state('u_rot_speed',0)
        self._processHandler.create_state('u_offset_angle',0)
        self._processHandler.create_state('p_time',0)
        self.program['u_rot_speed'] = self._processHandler.get_state_from(self._processHandler.name,'u_rot_speed')
        self.program['u_offset_angle'] = self._processHandler.get_state_from(self._processHandler.name,'u_offset_angle')
        self._last_cmd_time = self._processHandler.get_state_from(self._processHandler.name,'p_time')

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
        gloo.clear([0,1,0,0])

        # self.program['u_radius'] = self._processHandler.get_state_from(self._processHandler.name,'u_radius')
        cmd_time = self._processHandler.get_state_from(self._processHandler.name, 'p_time')
        if self._last_cmd_time != cmd_time:
            self._last_cmd_time = cmd_time
            self.program['u_rot_speed'] = self._processHandler.get_state_from(self._processHandler.name,'u_rot_speed')
            self.program['u_offset_angle'] = self._processHandler.get_state_from(self._processHandler.name,'u_offset_angle')
        self.program['u_time'] = self.timer.elapsed - self._last_cmd_time
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
    lock = Lock()
    GUI = TestGUI('testgui',lock=lock)
    GL_canvas = CanvasModule('OPENGL',lock=lock)
    GL_canvas.connect(GUI)
    logger = LoggerMinion('TestGUI logger',lock=lock)
    GUI.attach_logger(logger)
    GL_canvas.attach_logger(logger)
    logger.run()
    GUI.run()
    GL_canvas.run()