from time import perf_counter,sleep

import numpy as np
import serial
from pysinewave import SineWave

from bin.minion import BaseMinion, AbstractMinionMixin, TimerMinion
from bin.gui import DataframeTable
import traceback

import PyQt5.QtWidgets as qw
import PyQt5.QtCore as qc
from PyQt5.Qt import Qt as qt
from vispy import app, gloo


class ProtocolCommander(qw.QMainWindow, AbstractMinionMixin):
    def __init__(self, processHandler: BaseMinion = None, windowSize=(1200, 400), refresh_interval=10):
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
        self._processHandler.create_state('is_running',False)

        self.timer_switcher = qw.QPushButton('Start')
        self.timer_switcher.clicked.connect(self.switch_timer)

        self.frames = {}
        self.tables = {}
        self.addTableBox('Audio')
        self.addTableBox('Visual')
        self.addTableBox('Servo')
        self.groupbox_layout = qw.QHBoxLayout()
        for val in self.frames.values():
            self.groupbox_layout.addWidget(val)

        self.servo_slider = qw.QSlider(qt.Horizontal)
        self.servo_slider.setMinimum(0)
        self.servo_slider.setMaximum(180)
        self.servo_slider.valueChanged.connect(self.write_servo_pin)

        self.layout = qw.QVBoxLayout()
        self.layout.addLayout(self.groupbox_layout)
        self.layout.addWidget(self.timer_switcher)
        self.layout.addWidget(self.servo_slider)

        self.main_widget = qw.QWidget()
        self.main_widget.setLayout(self.layout)
        self.setCentralWidget(self.main_widget)

        self.sinewave = None

        self.protocol_params = {}
        self.protocols = {}

        self._watching_state = {}

        self._init_menu()

    def write_servo_pin(self,val):
        self._processHandler.set_state_to('servo', 'd:8:s', (val/180))

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
        self._processHandler.set_state_to(self._processHandler.name,'is_running',True)
        self._processHandler.set_state_to('OPENGL','u_offset_angle',0)
        self._processHandler.set_state_to('OPENGL','u_rot_speed',0)
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
        self._processHandler.set_state_to(self._processHandler.name,'is_running',False)
        self.sinewave.stop()
        self._processHandler.set_state_to('OPENGL','u_offset_angle',0)
        self._processHandler.set_state_to('OPENGL','u_rot_speed',0)
        sleep(.1)
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

        try:
            data = self.tables['Servo'].model()._data
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
                    if self.watch_state('servo_row',row_idx):
                        self._processHandler.set_state_to('servo','d:8:s',float(data['d:8:s'][row_idx])/90)
                        self.tables['Servo'].selectRow(row_idx)
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
                float edgeWidth = 0.04;
                return (smoothstep(0.,edgeWidth,st.x) - smoothstep(width,width+edgeWidth,st.x)) * (smoothstep(0.,edgeWidth, st.y) - smoothstep(height,height+edgeWidth,st.y));
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
                float grating = sin(20.*PI*st.x+40.*PI*st.y-u_time*50.)/2.; 
                vec3 color = vec3(red_saber,0.,blue_saber)+vec3((red_saber+blue_saber)*(grating/1.5));
                gl_FragColor = vec4(color,1.0);                
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
        self._last_cmd_time = None

    def on_timer(self, event):

        # if self.timer.elapsed - self._setTime > .01:  # Limit the call frequency to 1 second
        #
        #     # self._processHandler.set_state_to(self._processHandler.name, 'u_radius', np.sin(self.timer.elapsed))
        #     # Check if any remote calls have been set first before further processing
        #     if self._processHandler.status == -1:
        #         self._rmtShutdown = True
        #         self.on_close()
        #     elif self._processHandler.status == 0:
        #         self.on_close()

        self._setTime = np.floor(self.timer.elapsed)
        self.update()

    def on_draw(self, event):
        # Define the update rule
        try:
            gloo.clear([0,0,0,0])

            # self.program['u_radius'] = self._processHandler.get_state_from(self._processHandler.name,'u_radius')
            is_running = self._processHandler.get_state_from('testgui','is_running')
            if is_running:
                self._last_cmd_time = self._processHandler.get_state_from(self._processHandler.name, 'p_time')
                self.program['u_rot_speed'] = self._processHandler.get_state_from(self._processHandler.name,'u_rot_speed')
                self.program['u_offset_angle'] = 0
                self.program['u_time'] = self.timer.elapsed - self._last_cmd_time
                self.program.draw('triangle_strip')
            else:
                self._last_cmd_time = None
        except:
            print(traceback.format_exc())

    def on_resize(self, event):
        # Define how should be rendered image should be resized by changing window size
        gloo.set_viewport(0, 0, *self.physical_size)
        self.program['u_resolution'] = (self.size[0],self.size[1])

    def on_close(self):
        if not self._rmtShutdown:
            self._processHandler.set_state_to(self._processHandler.name, 'status', -1)
        self.close()

class ServoDriver(TimerMinion):

    def initialize(self):
        self._port_name = 'COM6'
        self.servos = {'d:8:s':1}

        try:
            self.init_polulo()
            self._watching_state = {}
            for n,v in self.servos.items():
                try:
                    self.create_state(n, self.getPosition(v))
                except:
                    print(traceback.format_exc())
        except:
            print(traceback.format_exc())


    ###### The following are copied from https://github.com/FRC4564/Maestro/blob/master/maestro.py with MIT license
    def init_polulo(self):
        self._port = serial.Serial(self._port_name)
        # Command lead-in and device number are sent for each Pololu serial command.
        self.PololuCmd = chr(0xaa) + chr(0x0c)
        # Track target position for each servo. The function isMoving() will
        # use the Target vs Current servo position to determine if movement is
        # occuring.  Upto 24 servos on a Maestro, (0-23). Targets start at 0.
        self.Targets = [0] * 24
        # Servo minimum and maximum targets can be restricted to protect components.
        self.Mins = [0] * 24
        self.Maxs = [0] * 24

        # Cleanup by closing USB serial port

    def sendCmd(self, cmd):
        cmdStr = self.PololuCmd + cmd
        self._port.write(bytes(cmdStr, 'latin-1'))

        # Set channels min and max value range.  Use this as a safety to protect
        # from accidentally moving outside known safe parameters. A setting of 0
        # allows unrestricted movement.
        #
        # ***Note that the Maestro itself is configured to limit the range of servo travel
        # which has precedence over these values.  Use the Maestro Control Center to configure
        # ranges that are saved to the controller.  Use setRange for software controllable ranges.

    def setRange(self, chan, min, max):
        self.Mins[chan] = min
        self.Maxs[chan] = max

        # Return Minimum channel range value

    def getMin(self, chan):
        return self.Mins[chan]

        # Return Maximum channel range value

    def getMax(self, chan):
        return self.Maxs[chan]

        # Set channel to a specified target value.  Servo will begin moving based
        # on Speed and Acceleration parameters previously set.
        # Target values will be constrained within Min and Max range, if set.
        # For servos, target represents the pulse width in of quarter-microseconds
        # Servo center is at 1500 microseconds, or 6000 quarter-microseconds
        # Typcially valid servo range is 3000 to 9000 quarter-microseconds
        # If channel is configured for digital output, values < 6000 = Low ouput

    def setTarget(self, chan, target):
        # if Min is defined and Target is below, force to Min
        if self.Mins[chan] > 0 and target < self.Mins[chan]:
            target = self.Mins[chan]
        # if Max is defined and Target is above, force to Max
        if self.Maxs[chan] > 0 and target > self.Maxs[chan]:
            target = self.Maxs[chan]
        #
        lsb = target & 0x7f  # 7 bits for least significant byte
        msb = (target >> 7) & 0x7f  # shift 7 and take next 7 bits for msb
        cmd = chr(0x04) + chr(chan) + chr(lsb) + chr(msb)
        self.sendCmd(cmd)
        # Record Target value
        self.Targets[chan] = target

        # Set speed of channel
        # Speed is measured as 0.25microseconds/10milliseconds
        # For the standard 1ms pulse width change to move a servo between extremes, a speed
        # of 1 will take 1 minute, and a speed of 60 would take 1 second.
        # Speed of 0 is unrestricted.

    def setSpeed(self, chan, speed):
        lsb = speed & 0x7f  # 7 bits for least significant byte
        msb = (speed >> 7) & 0x7f  # shift 7 and take next 7 bits for msb
        cmd = chr(0x07) + chr(chan) + chr(lsb) + chr(msb)
        self.sendCmd(cmd)

        # Set acceleration of channel
        # This provides soft starts and finishes when servo moves to target position.
        # Valid values are from 0 to 255. 0=unrestricted, 1 is slowest start.
        # A value of 1 will take the servo about 3s to move between 1ms to 2ms range.

    def setAccel(self, chan, accel):
        lsb = accel & 0x7f  # 7 bits for least significant byte
        msb = (accel >> 7) & 0x7f  # shift 7 and take next 7 bits for msb
        cmd = chr(0x09) + chr(chan) + chr(lsb) + chr(msb)
        self.sendCmd(cmd)

        # Get the current position of the device on the specified channel
        # The result is returned in a measure of quarter-microseconds, which mirrors
        # the Target parameter of setTarget.
        # This is not reading the true servo position, but the last target position sent
        # to the servo. If the Speed is set to below the top speed of the servo, then
        # the position result will align well with the acutal servo position, assuming
        # it is not stalled or slowed.

    def getPosition(self, chan):
        cmd = chr(0x10) + chr(chan)
        self.sendCmd(cmd)
        lsb = ord(self._port.read())
        msb = ord(self._port.read())
        return (msb << 8) + lsb

        # Test to see if a servo has reached the set target position.  This only provides
        # useful results if the Speed parameter is set slower than the maximum speed of
        # the servo.  Servo range must be defined first using setRange. See setRange comment.
        #
        # ***Note if target position goes outside of Maestro's allowable range for the
        # channel, then the target can never be reached, so it will appear to always be
        # moving to the target.

    def isMoving(self, chan):
        if self.Targets[chan] > 0:
            if self.getPosition(chan) != self.Targets[chan]:
                return True
        return False

        # Have all servo outputs reached their targets? This is useful only if Speed and/or
        # Acceleration have been set on one or more of the channels. Returns True or False.
        # Not available with Micro Maestro.

    def getMovingState(self):
        cmd = chr(0x13)
        self.sendCmd(cmd)
        if self._port.read() == chr(0):
            return False
        else:
            return True

        # Run a Maestro Script subroutine in the currently active script. Scripts can
        # have multiple subroutines, which get numbered sequentially from 0 on up. Code your
        # Maestro subroutine to either infinitely loop, or just end (return is not valid).

    def runScriptSub(self, subNumber):
        cmd = chr(0x27) + chr(subNumber)
        # can pass a param with command 0x28
        # cmd = chr(0x28) + chr(subNumber) + chr(lsb) + chr(msb)
        self.sendCmd(cmd)

        # Stop the current Maestro Script

    def stopScript(self):
        cmd = chr(0x24)
        self.sendCmd(cmd)

    def on_time(self):
        try:
            for n,v in self.servos.items():
                state = self.get_state_from(self.name,n)
                if self.watch_state(n,state) and state is not None:
                    self.setTarget(v,int(state*4000+4000))
                    # v.write(state*180)
        except:
            print(traceback.format_exc())

    def shutdown(self):
        self._port.close()


    def watch_state(self,name,val):
        if name not in self._watching_state.keys():
            self._watching_state[name] = val
            return True
        else:
            changed = val != self._watching_state[name]
            self._watching_state[name] = val
            return changed
