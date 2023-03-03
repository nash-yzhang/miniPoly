import os
from time import perf_counter, sleep

import cv2
import numpy as np

from bin.minion import BaseMinion, AbstractMinionMixin, TimerMinionMixin, TimerMinion
from definition import ROOT_DIR

import serial
import traceback

import PyQt5.QtWidgets as qw
import PyQt5.QtCore as qc
from PyQt5.Qt import Qt as qt
from PyQt5.QtGui import QIcon, QPixmap
from vispy import app, gloo

import pyfirmata as fmt

import ctypes
from src.tisgrabber import tisgrabber as tis

import csv


class AbstractCompiler(TimerMinionMixin):
    _processHandler: TimerMinion

    def __init__(self, processHandler: TimerMinion):
        super().__init__()
        self._processHandler = processHandler
        self._processHandler.add_callback('default', self._on_time)
        self.refresh_interval = self._processHandler.refresh_interval
        self.name = self._processHandler.name

    def _on_time(self, t):
        if self.status() <= 0:
            self._on_close()
        try:
            self.on_time(t)
        except:
            self.error('Error in on_time')
            self.debug(traceback.format_exc())
        self._processHandler.on_time(t)

    def on_time(self, t):
        pass

    def on_protocol(self, t):
        pass

    def _on_close(self):
        self.set_state('status', -1)
        self.on_close()

    def on_close(self):
        pass


class QtCompiler(AbstractCompiler, qw.QMainWindow):

    def __init__(self, processHandler, **kwargs):
        AbstractCompiler.__init__(self, processHandler)
        qw.QMainWindow.__init__(self, **kwargs)
        self.setWindowTitle(self.name)
        self.setWindowIcon(QIcon(ROOT_DIR + '/bin/minipoly.ico'))
        self.renderSplashScreen()

    def renderSplashScreen(self):
        splash_pix = QPixmap(ROOT_DIR + '/bin/minipoly.ico')
        splash = qw.QSplashScreen(splash_pix, qc.Qt.WindowStaysOnTopHint)
        # add fade to splashscreen
        splash.show()
        for i in range(20):
            splash.setWindowOpacity(1.5 - abs(1.5 - (i / 10)))
            sleep(0.05)
        splash.close()  # close the splash screen


class GLCompiler(app.Canvas, AbstractMinionMixin):

    def __init__(self, processHandler, *args, protocol_commander: BaseMinion = None,
                 VS=None, FS=None, refresh_interval=10, **kwargs):
        super().__init__(*args, **kwargs)
        # app.Canvas.__init__(self, *args, **kwargs)
        self._processHandler = processHandler
        self.timers = {'default': app.Timer(refresh_interval / 1000, self._on_timer, start=True),
                       'protocol': app.Timer(refresh_interval / 1000, self._on_protocol, start=False)}
        self._protocol_time_name = 'p_time'
        self.protocol_time_offset = None
        self.VS = None
        self.FS = None
        self.program = None
        self._shared_uniform_states = []

        self.protocol_commander = protocol_commander

        if VS:
            self.load_VS(VS)
        if FS:
            self.load_FS(FS)

        if self.VS is not None and self.FS is not None:
            self.program = gloo.Program(self.VS, self.FS)

    def register_protocol_commander(self, protocol_commander: BaseMinion):
        self._processHandler.connect(protocol_commander)
        self.protocol_commander = protocol_commander.name

    def load_shader_file(self, fn):
        with open(fn, 'r') as shaderfile:
            return (shaderfile.read())

    def load_VS(self, fn):
        self.VS = self.load_shader_file(fn)

    def load_FS(self, fn):
        self.FS = self.load_shader_file(fn)

    def load_shaders(self, vsfn, fsfn):
        self.load_VS(vsfn)
        self.load_FS(fsfn)
        self.program = gloo.Program(self.VS, self.FS)

    def create_shared_uniform_state(self, type='uniform'):
        for i in self.program.variables:
            if i[2] not in ['u_resolution', 'u_time']:
                if type != 'all':
                    if i[0] == type:
                        try:
                            self.create_state(i[2], list(self.program[i[2]].astype(float)))
                        except KeyError:
                            self.warning(f'Uniform {i[2]} has not been set: {i[2]}\n{traceback.format_exc()}')
                            if i[1] == 'vec2':
                                self.create_state(i[2], [0, 0])
                            elif i[1] == 'vec3':
                                self.create_state(i[2], [0, 0, 0])
                            elif i[1] == 'vec4':
                                self.create_state(i[2], [0, 0, 0, 0])
                            else:
                                self.create_state(i[2], 0)
                        except:
                            self.error(f'Error in creating shared state for uniform: {i[2]}\n{traceback.format_exc()}')
                        self._shared_uniform_states.append(i[2])
                else:
                    if i[0] not in ['varying', 'constant']:
                        self.create_state(i[2], self.program[i[2]])
                        self._shared_uniform_states.append(i[2])

    def check_variables(self):
        redundant_variables = list(self.program._pending_variables.keys())
        unsettled_variables = []
        for i in self.program.variables:
            if i[0] not in ['varying', 'constant']:
                if i[2] not in self.program._user_variables.keys():
                    unsettled_variables.append(i[2])
        return redundant_variables, unsettled_variables

    def initialize(self):
        self.create_state(self._protocol_time_name, 0)
        self.create_state('fullScreen', False)
        self.fullscreen = self.get_state('fullScreen')
        self.on_init()
        if self.program is not None:
            rv, uv = self.check_variables()
            if uv:
                self.error(f'Found {len(rv)} unsettled variables: {uv}')
            if rv:
                self.warning(f'Found {len(rv)} pending variables: {rv}')
            self.create_shared_uniform_state(type='uniform')
        else:
            self.error(f'Rendering program has not been built!')
            self.close()

    def _on_timer(self, event):
        if self.status() <= 0:
            self.on_close()
        self.on_timer(event)
        self.fullscreen = self.get_state('fullScreen')

    def on_timer(self, event):
        pass

    def _on_protocol(self, event):
        self.protocol_time_offset = self.get_state(self._protocol_time_name)
        self.on_protocol(event, self.protocol_time_offset)

    def on_protocol(self, event, offset):
        pass

    def on_init(self):
        pass

    def is_protocol_running(self):
        return self.timers['protocol'].running

    def run_protocol(self):
        self.start_timing('protocol')

    def stop_protocol(self):
        self.stop_timing('protocol')
        gloo.clear('black')
        self.update()

    def start_timing(self, timer_name='default'):
        if type(timer_name) is str:
            if timer_name == 'all':
                for k in self.timers.keys():
                    self.timers[k].start()
            else:
                if timer_name in self.timers.keys():
                    self.timers[timer_name].start()
                else:
                    self.error(f'NameError: Unknown timer name: {timer_name}')
        elif type(timer_name) is list:
            for n in timer_name:
                if n in self.timers.keys():
                    self.timers[n].start()
                else:
                    self.error(f'NameError: Unknown timer name: {n}')
        else:
            self.error(f'TypeError: Invalid timer name: {timer_name}')

    def stop_timing(self, timer_name='default'):
        if type(timer_name) is str:
            if timer_name == 'all':
                for k in self.timers.keys():
                    self.timers[k].stop()
            else:
                if timer_name in self.timers.keys():
                    self.timers[timer_name].stop()
                else:
                    self.error(f'NameError: Unknown timer name: {timer_name}')
        elif type(timer_name) is list:
            for n in timer_name:
                if n in self.timers.keys():
                    self.timers[n].stop()
                else:
                    self.error(f'NameError: Unknown timer name: {n}')
        else:
            self.error(f'TypeError: Invalid timer name: {timer_name}')

    def on_draw(self, event):
        pass

    def on_resize(self, event):
        # Define how should be rendered image should be resized by changing window size
        gloo.set_viewport(0, 0, *self.physical_size)
        self.program['u_resolution'] = (self.size[0], self.size[1])

    def on_close(self):
        self.set_state('status', -1)
        self.close()


class PololuServoCompiler(AbstractCompiler):
    AUXile_Postfix = "Pololu_AUX"

    def __init__(self, *args, port_name='COM6', servo_dict={}, **kwargs):
        super(PololuServoCompiler, self).__init__(*args, **kwargs)
        self._port_name = port_name
        self.servo_dict = servo_dict

        self.streaming = False
        self._AUX_FileHandle = None
        self._AUX_writer = None
        self._stream_init_time = None

        self.init_pololu()
        for i in range(24):
            self.setRange(i, 2500, 10000)
        self._watching_state = {}
        for n, v in self.servo_dict.items():
            try:
                self.create_state(n, self.getPosition(v))
            except:
                print(traceback.format_exc())
        self.create_state('StreamToDisk', False)
        self.create_state('SaveDir', False)
        self.create_state('SaveName', False)
        self.create_state('InitTime', False)

    def on_time(self, t):
        self._streaming_setup()
        for n, v in self.servo_dict.items():
            state = self.get_state(n)
            if self.watch_state(n, state) and state is not None:
                self.setTarget(v, int(state))
                # print(f"Set {n}-{v} to {state}")
        self._data_streaming()

    def _streaming_setup(self):
        if_streaming = self.get_state('StreamToDisk')
        if self.watch_state('StreamToDisk', if_streaming):
            if if_streaming:
                self._start_streaming()
            else:
                self._stop_streaming()

    def _start_streaming(self):
        save_dir = self.get_state('SaveDir')
        file_name = self.get_state('SaveName')
        init_time = self.get_state('InitTime')
        if save_dir is None or file_name is None or init_time is None:
            self.error("Please set the save directory, file name and initial time before streaming.")
        else:
            if os.path.isdir(save_dir):
                AUX_Fn = f"{self.name}_{file_name}_{self.AUXile_Postfix}.csv"
                AUX_Fulldir = os.path.join(save_dir, AUX_Fn)
                if os.path.isfile(AUX_Fulldir):
                    self.error(f"File {AUX_Fn} already exists in the folder {save_dir}. Please change "
                               f"the save_name.")
                else:
                    self._AUX_FileHandle = open(AUX_Fulldir, 'w')
                    self._AUX_writer = csv.writer(self._AUX_FileHandle)
                    col_name = ['Time']
                    for n in self.servo_dict.keys():
                        col_name.append(n)
                    self._AUX_writer.writerow(col_name)
                    self._stream_init_time = init_time
                    self.streaming = True

    def _stop_streaming(self):
        if self._AUX_FileHandle is not None:
            self._AUX_FileHandle.close()
        self._AUX_writer = None
        self._stream_init_time = None
        self._n_frame_streamed = None
        self.streaming = False

    def _data_streaming(self):
        if self.streaming:
            # Write to AUX file
            col_val = [perf_counter() - self._stream_init_time]
            for n in self.servo_dict.keys():
                col_val.append(self.get_state(n))
            self._AUX_writer.writerow(col_val)

    def on_close(self):
        self._port.close()

    ###### The following are copied from https://github.com/FRC4564/Maestro/blob/master/maestro.py with MIT license
    def init_pololu(self):
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

    #############################################################################################


class SerialCommandCompiler(AbstractCompiler):

    def __init__(self, *args, port_name='COM7', baud=9600, timeout=0.001, **kwargs):
        super(SerialCommandCompiler, self).__init__(*args, **kwargs)
        self._port_name = port_name
        self._baud = baud
        self._timeout = timeout
        self._port = None

        self._port = serial.Serial(self._port_name, self._baud, timeout=self._timeout)
        self.create_state('serial', 0)

    def on_time(self, t):
        try:
            state = self.get_state('serial')
            if self.watch_state('serial', state) and state is not None:
                if state == 0:
                    self._port.write(b'2')
                elif state == 1:
                    self._port.write(b'1')
        except:
            print(traceback.format_exc())

    def on_close(self):
        self.set_state('status', -1)
        self._port.close()


class ArduinoCompiler(AbstractCompiler):

    def __init__(self, *args, port_name='COM7', pin_address={}, **kwargs):
        super(ArduinoCompiler, self).__init__(*args, **kwargs)
        self._port_name = port_name
        self.pin_address = pin_address
        self._port = None
        self.pin_dict = {}

        try:
            self._port = fmt.Arduino(self._port_name)
            self._watching_state = {}
            for n, v in self.pin_address.items():
                try:
                    self.pin_dict[n] = self._port.get_pin(v)
                    self.create_state(n, self.pin_dict[n].read())
                except:
                    print(traceback.format_exc())
        except:
            print(traceback.format_exc())

    def on_time(self, t):
        for n, v in self.pin_dict.items():
            state = self.get_state(n)
            if self.watch_state(n, state) and state is not None:
                v.write(state)

    def on_close(self):
        self.set_state('status', -1)
        self._port.exit()


class TISCameraCompiler(AbstractCompiler):
    TIS_DLL_DIR = "../src/tisgrabber/tisgrabber_x64.dll"
    TIS_Width = ctypes.c_long()
    TIS_Height = ctypes.c_long()
    TIS_BitsPerPixel = ctypes.c_int()
    TIS_colorformat = ctypes.c_int()

    BINFile_Postfix = "IC_IMG"
    AUXile_Postfix = "IC_AUX"

    def __init__(self, *args, camera_name=None, save_option='binary', **kwargs):
        super(TISCameraCompiler, self).__init__(*args, **kwargs)

        self.frame_rate = 1000 / self.refresh_interval
        self.ic = None
        self._camera_name = camera_name
        self._buffer_name = None
        self._buf_img = None
        self.frame_shape = None
        self._params = {"CameraName": None, 'VideoFormat': None,
                        'StreamToDisk': False, 'SaveDir': None, 'SaveName': None, 'InitTime': None,
                        'FrameCount': 0, 'FrameTime': 0}
        self.streaming = False
        self._BIN_FileHandle = None
        self._AUX_FileHandle = None
        self._AUX_writer = None
        self._stream_init_time = None
        self._n_frame_streamed = None

        if save_option in ['binary', 'movie']:
            self.save_option = save_option
        else:
            raise ValueError("save_option must be either 'binary' or 'movie'")

        for k, v in self._params.items():
            self.create_state(k, v)
        self._init_camera()
        self.info(f"Camera {self.name} initialized.")

    def _init_camera(self):
        self.info("Searching camera...")
        while self._params['CameraName'] is None:
            self._params['CameraName'] = self.get_state('CameraName')
        while self._params['VideoFormat'] is None:
            self._params['VideoFormat'] = self.get_state('VideoFormat')
        self.info(f"Camera {self._params['CameraName']} found")
        self.camera = tis.TIS_CAM()
        self.camera.DevName = self._params['CameraName']
        if self.camera.IsDevValid():
            self.camera.StopLive()
        self._camera_name = self.camera.DevName.replace(' ', '_')
        self.camera.open(self.camera.DevName)
        self.update_video_format()
        self.camera.SetContinuousMode(0)
        self.camera.StartLive(0)
        self.info(f"Camera {self._params['CameraName']} initialized")

    def update_video_format(self):
        video_format = self._params['VideoFormat']
        if self.camera.IsDevValid():
            self.camera.StopLive()
        self.camera.SetVideoFormat(self._params['VideoFormat'])
        buffer_name = f"frame_{self._params['VideoFormat']}".replace(' ', '_')
        self.camera.StartLive(0)
        self.camera.SnapImage()
        frame = self.camera.GetImage()
        self.frame_shape = frame.shape
        if self.has_buffer(buffer_name):
            self.set_buffer(buffer_name, frame)
        else:
            self.create_shared_buffer(buffer_name, frame)
        self._buffer_name = buffer_name
        self.camera.StopLive()

    def on_time(self, t):
        try:
            cameraName = self.get_state('CameraName')
            if self.watch_state('CameraName', cameraName):
                if cameraName is not None:
                    self._init_camera()
                else:
                    try:
                        self.disconnect_camera()
                        self.info("Camera disconnected")
                    except:
                        self.error("An error occurred while disconnecting the camera")
                        self.debug(traceback.format_exc())
            else:
                self._params['VideoFormat'] = self.get_state('VideoFormat')
                if self.watch_state('VideoFormat', self._params['VideoFormat']):
                    self.update_video_format()
                if self.camera.IsDevValid():
                    self.process_frame()
        except:
            self.error("An error occurred while updating the camera")

    def process_frame(self):
        self._streaming_setup()
        self.camera.SnapImage()
        frame_time = perf_counter()
        frame = self.camera.GetImage()
        self.set_buffer(self._buffer_name, frame)
        self._data_streaming(frame_time, frame)

    def _data_streaming(self, frame_time, frame):
        if self.streaming:
            frame_time = frame_time - self._stream_init_time
            # Write to AUX file
            n_frame = self._n_frame_streamed
            self._AUX_writer.writerow([n_frame, frame_time])

            if self.save_option == 'binary':
                # Write to BIN file
                self._BIN_FileHandle.write(bytearray(frame))
            elif self.save_option == 'movie':
                # Write to movie file
                self._BIN_FileHandle.write(frame)

            self._n_frame_streamed += 1
            self.set_state('FrameCount', self._n_frame_streamed)

    def _streaming_setup(self):
        if_streaming = self.get_state('StreamToDisk')
        if self.watch_state('StreamToDisk', if_streaming):  # Triggered at the onset and the end of streaming
            if if_streaming:
                self._start_streaming()
            else:  # close all files before streaming stops
                self._stop_streaming()

    def _start_streaming(self):
        save_dir = self.get_state('SaveDir')
        file_name = self.get_state('SaveName')
        init_time = self.get_state('InitTime')
        if save_dir is None or file_name is None or init_time is None:
            self.error("Please set the save directory, file name and initial time before streaming.")
        else:
            if os.path.isdir(save_dir):
                if self.save_option == 'binary':
                    BIN_Fn = f"{self._camera_name}_{file_name}_{self.BINFile_Postfix}.bin"
                    BIN_Fulldir = os.path.join(save_dir, BIN_Fn)
                elif self.save_option == 'movie':
                    BIN_Fn = f"{self._camera_name}_{file_name}_{self.BINFile_Postfix}.avi"
                    BIN_Fulldir = os.path.join(save_dir, BIN_Fn)
                AUX_Fn = f"{self._camera_name}_{file_name}_{self.AUXile_Postfix}.csv"
                AUX_Fulldir = os.path.join(save_dir, AUX_Fn)
                if os.path.isfile(BIN_Fulldir) or os.path.isfile(AUX_Fulldir):
                    self.error(f"File {BIN_Fn} or {AUX_Fn} already exists in the folder {save_dir}. Please change "
                               f"the save_name.")
                else:
                    if self.save_option == 'binary':
                        self._BIN_FileHandle = open(BIN_Fulldir, 'wb')
                    elif self.save_option == 'movie':
                        self._BIN_FileHandle = cv2.VideoWriter(BIN_Fulldir, cv2.VideoWriter_fourcc(*'MJPG'),
                                                               int(self.frame_rate),
                                                               (self.frame_shape[1], self.frame_shape[0]))

                    self._AUX_FileHandle = open(AUX_Fulldir, 'w')
                    self._AUX_writer = csv.writer(self._AUX_FileHandle)
                    self._stream_init_time = init_time
                    self._n_frame_streamed = 0
                    self.streaming = True

    def _stop_streaming(self):
        if self._BIN_FileHandle is not None:
            if self.save_option == 'binary':
                self._BIN_FileHandle.close()
            elif self.save_option == 'movie':
                self._BIN_FileHandle.release()
        if self._AUX_FileHandle is not None:
            self._AUX_FileHandle.close()
        self._AUX_writer = None
        self._stream_init_time = None
        self._n_frame_streamed = None
        self.streaming = False

    def disconnect_camera(self):
        self.camera.StopLive()
        self.camera = tis.TIS_CAM()
        self._params = {"CameraName": None, 'VideoFormat': None,
                        'Trigger': 0, 'FrameCount': 0, 'FrameTime': 0}

    def on_close(self):
        if self.camera.IsDevValid():
            self.disconnect_camera()
            self.camera = None
