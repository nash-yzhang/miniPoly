import traceback
from time import sleep

import numpy as np
from pysinewave import SineWave

from miniPoly.prototype.Logging import LoggerMinion
from miniPoly.prototype.GL import AbstractGLAPP
from miniPoly.prototype.GUI import AbstractGUIAPP
from miniPoly.util.gui import DataframeTable
from miniPoly.compiler.graphics import QtCompiler, GLCompiler
import PyQt5.QtWidgets as qw
from vispy import gloo

class ProtocolCommander(QtCompiler):
    def __init__(self, *args, windowSize=(900,300),**kwargs):
        super().__init__(*args, **kwargs)
        self.add_timer('protocol_timer',self.on_protocol)
        self.create_state('is_running',False)

        self._timer_started = False
        self.timer_switcher = qw.QPushButton('Start')
        self.timer_switcher.clicked.connect(self.switch_timer)
        self.resize(*windowSize)

        self.frames = {}
        self.tables = {}
        self.addTableBox('Audio')
        self.addTableBox('Visual')
        # self.addTableBox('Servo')
        self.groupbox_layout = qw.QHBoxLayout()
        for val in self.frames.values():
            self.groupbox_layout.addWidget(val)

        # self.servo_slider = qw.QSlider(qt.Horizontal)
        # self.servo_slider.setMinimum(0)
        # self.servo_slider.setMaximum(180)
        # self.servo_slider.valueChanged.connect(self.write_servo_pin)

        self.layout = qw.QVBoxLayout()
        self.layout.addLayout(self.groupbox_layout)
        self.layout.addWidget(self.timer_switcher)
        # self.layout.addWidget(self.servo_slider)

        self.main_widget = qw.QWidget()
        self.main_widget.setLayout(self.layout)
        self.setCentralWidget(self.main_widget)

        self.sinewave = None

        self._init_menu()

    # def write_servo_pin(self,val):
    #     self.set_state_to('servo', 'd:8:s', (val/180))

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
        self.set_state('is_running',True)
        self.set_state_to('OPENGL','u_offset_angle',0)
        self.set_state_to('OPENGL','u_rot_speed',0)
        data = self.tables['Audio'].model()._data
        self.sinewave = SineWave(pitch=data['p_freq'][0],
                                 pitch_per_second=2000,
                                 decibels_per_second=2000)
        self.sinewave.play()
        # pass

    def _stopTimer(self):
        self.stopTimer()
        self.stop_timing('protocol_timer')
        self._timer_started = False  # self._time = self._time.elapsed()
        self.timer_switcher.setText('Start')

    def stopTimer(self):
        self.set_state('is_running',False)
        self.sinewave.stop()
        self.set_state_to('OPENGL','u_offset_angle',0)
        self.set_state_to('OPENGL','u_rot_speed',0)
        sleep(.1)
        # pass

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
                        p_time = data['time'][row_idx].astype(float)
                        u_rot_speed = data['u_rot_speed'][row_idx].astype(float)
                        while True:
                            try:
                                self.set_state_to('OPENGL','p_time',p_time)
                                self.set_state_to('OPENGL','u_rot_speed',u_rot_speed)
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
            if cur_time <= (time_col.max() + self.timerInterval()):
                row_idx = None
                for i,v in enumerate(time_col):
                    if v >= cur_time:
                        row_idx = i-1
                        break
                if row_idx is None:
                    self._stopTimer()
                else:
                    if self.watch_state('audio_row',row_idx):
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
        #     data = self.tables['Servo'].model()._data
        #     time_col = data['time']
        #     if cur_time <= (time_col.max() + self.timerInterval()):
        #         row_idx = None
        #         for i,v in enumerate(time_col):
        #             if v >= cur_time:
        #                 row_idx = i-1
        #                 break
        #         if row_idx is None:
        #             self._stopTimer()
        #         else:
        #             if self.watch_state('servo_row',row_idx):
        #                 self.set_state_to('servo','d:8:s',float(data['d:8:s'][row_idx])/90)
        #                 self.tables['Servo'].selectRow(row_idx)
        #                 self.row_idx = row_idx
        #     else:
        #         self._stopTimer()
        # except:
        #     print(traceback.format_exc())
        #     self.tables['Audio'].clearSelection()

    def _init_menu(self):
        self._menubar = self.menuBar()
        self._menu_file = self._menubar.addMenu('File')
        Exit = qw.QAction("Quit", self)
        Exit.setShortcut("Ctrl+Q")
        Exit.setStatusTip("Exit program")
        Exit.triggered.connect(self.close)
        self._menu_file.addAction(Exit)

class GraphicProtocolCompiler(GLCompiler):

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)

    def on_init(self):
        self.program['a_pos'] = np.array([[-1., -1.], [-1., 1.], [1., -1.], [1., 1.]], np.float32)  # /2.
        self.program['u_time'] = 0
        self.program['u_offset_angle'] = 0.
        self.program['u_rot_speed'] = 0.

        gloo.set_state("translucent")
        self.program['u_resolution'] = (self.size[0], self.size[1])
        self.create_state('num_cmd_compiled',0)
        self.create_state('num_cmd_sent',0)

    def on_timer(self, event):
        if not self.is_protocol_running():
            is_running = self.get_state_from('testgui', 'is_running')
            if is_running:
                self.run_protocol()

    def on_protocol(self,event,offset):
        self.program['u_time'] = event.elapsed - offset
        self.program['u_rot_speed'] = self.get_state('u_rot_speed')
        self.program['u_offset_angle'] = 0
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
        self._win = GraphicProtocolCompiler(self,app=self._app,VS='../APP/protocol_compiler/test.VS',FS='../APP/protocol_compiler/test.FS',refresh_interval=5)
        self.info('Starting display window')
        self._win.initialize()
        self._win.show()



if __name__ == '__main__':
    GUI = TestGUI('testgui')
    GL_canvas = CanvasModule('OPENGL')
    # servo = ServoDriver('servo')
    GL_canvas.connect(GUI)
    # GUI.connect(servo)
    logger = LoggerMinion('TestGUI logger')
    GUI.attach_logger(logger)
    GL_canvas.attach_logger(logger)
    # servo.attach_logger(logger)
    logger.run()
    # servo.run()
    GL_canvas.run()
    GUI.run()
