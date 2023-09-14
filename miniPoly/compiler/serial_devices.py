import traceback

import numpy as np
import pandas as pd
import pyfirmata2 as fmt
import serial
import usb.core
import usb.util

from miniPoly.compiler.prototypes import AbstractCompiler, StreamingCompiler

class PololuServoInterface(StreamingCompiler):
    MOUSE_SERVO_DISTANCE = 150 # distance between the mouse and the servo in mm
    ARM0_LENGTH = 40 # length of the first arm in mm
    ARM1_LENGTH = 90 # length of the second arm in mm
    EXTENDED_LENGTH = 100


    @staticmethod
    def servo_angle_solver(target_azi, target_r):
        # the inputs and outputs are both in degrees
        target_azi *= np.pi / 180
        servo_azi = np.pi/2 - np.arctan(np.cos(target_azi) / (PololuServoInterface.MOUSE_SERVO_DISTANCE / target_r + np.sin(target_azi)))
        total_length = (PololuServoInterface.MOUSE_SERVO_DISTANCE + target_r * np.sin(target_azi)) / np.sin(servo_azi) - PololuServoInterface.EXTENDED_LENGTH
        servo_r = np.arccos((PololuServoInterface.ARM0_LENGTH ** 2 + total_length ** 2 - PololuServoInterface.ARM1_LENGTH ** 2) / (2 * PololuServoInterface.ARM0_LENGTH * total_length)) - np.pi/2
        return servo_azi, servo_r

    def __init__(self, *args, port_name='COM6', servo_dict={}, **kwargs):
        super(PololuServoInterface, self).__init__(*args, **kwargs)
        self._port = None
        self._port_name = port_name
        self.servo_dict = servo_dict
        self.servo_param = {}

        self.streaming = False
        self._AUX_FileHandle = None
        self._AUX_writer = None
        self._stream_init_time = None

        self.target_azi = None
        self.target_r = None

        self._azi = 0.5
        self._r = 0.5

        self.init_pololu()
        # for i in range(24):
        #     self.setRange(i, 2500, 10000)
        self._watching_state = {}
        for n, v in self.servo_dict.items():
            try:
                self.create_streaming_state(n, -1, shared=True)
                self.servo_param[n] = [v[1], v[2]]
                self.servo_dict[n] = v[0]
            except:
                print(traceback.format_exc())
        # self.create_state('StreamToDisk', False)
        # self.create_state('SaveDir', False)
        # self.create_state('SaveName', False)
        # self.create_state('InitTime', False)

    def on_time(self, t):
        # yaw = self.getPosition(self.servo_dict['yaw'])
        # radius = self.getPosition(self.servo_dict['radius'])
        # print(f"Yaw: {yaw}, Radius: {radius}")
        should_update = False
        for n, v in self.servo_dict.items():
            state = self.get_state(n)
            if self.watch_state(n, state) and state is not None:
                if n == 'yaw':
                    self.target_azi = state
                    if self.target_r is not None:
                        should_update = True
                elif n == 'radius':
                    self.target_r = state
                    if self.target_azi is not None:
                        should_update = True
                else:
                    iter_min, iter_max = self.servo_param[n][0], self.servo_param[n][1]
                    new_pos = int(state*(iter_max-iter_min) + iter_min)
                    self.setTarget(v, new_pos)

        if should_update:
            azi, radius = self.servo_angle_solver(self.target_azi, self.target_r)
            azi = azi/np.pi
            radius = .5+radius/np.pi
            print(f'Azimuth: {azi}, radius: {radius}')
            # azi, radius = self.target_azi, self.target_r
            yaw_min, yaw_max = self.servo_param['yaw'][0], self.servo_param['yaw'][1]
            radius_min, radius_max = self.servo_param['radius'][0], self.servo_param['radius'][1]
            self._azi = int(yaw_min + azi*(yaw_max-yaw_min))
            self._r = int(radius_min + radius*(radius_max-radius_min))
        self.setTarget(self.servo_dict['yaw'], self._azi)
        self.setTarget(self.servo_dict['radius'], self._r)

        super().on_time(t)

    def on_close(self):
        self._port.close()
        self.set_state('status', -1)

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


class SerialCommandCompiler(StreamingCompiler):

    def __init__(self, *args, port_name='COM7', baud=9600, timeout=0.001, **kwargs):
        super(SerialCommandCompiler, self).__init__(*args, **kwargs)
        self._port_name = port_name
        self._baud = baud
        self._timeout = timeout
        self._port = None

        self._port = serial.Serial(self._port_name, self._baud, timeout=self._timeout)

    def on_time(self, t):
        super().on_time(t)

class MotorShieldCompiler(SerialCommandCompiler):
    RADIUS_SERVO_MIN = 15
    MASK_OFF_ANGLE = [0, 180]
    MASK_ON_ANGLE = [170, 15]

    def __init__(self, processHandler, motor_dict={}, **kwargs):
        super(MotorShieldCompiler, self).__init__(processHandler, **kwargs)
        self._motor_dict = motor_dict
        for k in self._motor_dict.keys():
            self.create_streaming_state(k, 0, shared=False,use_buffer=False)

        self._mask_status = np.array([False, False])

        self.watch_state('runSignal', False)
        self._running_protocol = False

        self.create_streaming_state('protocolFn', '', shared=False, use_buffer=False)
        self.watch_state('protocolFn', '')

        # The following shared state are for debugging
        self.create_state('serial_cmd', '')
        self.watch_state('serial_cmd', '')

        self.watch_state('cmd_idx',-1)
        self.create_streaming_state('cmd_idx', -1, shared=True, use_buffer=True)
        self._protocolFn = ''
        self._protocol = None
        self._protocol_start_time = None
        self._time_index_col = None
        self._cmd_idx_lookup_table = None
        self._running_time = 0

        self._stepper_counter = 0

    def on_time(self,t):
        self.get_protocol_fn()
        running = self.get_run_signal()
        if running:
            self._run_protocol()
        else:
            if self._protocol_start_time is not None:
                self._end_protocol()
            else:
                serial_cmd = self.get_state('serial_cmd')
                if self.watch_state('serial_cmd', serial_cmd):
                    self._port.write(serial_cmd.encode())
                    self.info(f"Execute serial cmd: {self.get_state('serial_cmd')}")

        super().on_time(t)

    def reset_servo_status(self):
        pass

    def get_protocol_fn(self):
        if self._protocol_start_time is None:  # Only execute if protocol is not running
            protocolFn = self.get_state_from(self._trigger_minion,'protocolFn')
            if self.watch_state('protocolFn', protocolFn) and protocolFn not in ['', None]:
                self.info(f"Loading protocol from {protocolFn}")
                self._protocol = pd.read_excel(protocolFn)
                self._protocolFn = protocolFn
                self._time_index_col = self._protocol['time'].to_numpy()
                self._cmd_idx_lookup_table = {k: [self._motor_dict[k],i] for i, k in enumerate(self._protocol.columns) if k in self._motor_dict.keys()}

    def get_run_signal(self):
        if self._protocolFn is not None:  # Only execute if protocol is loaded
            runSignal = self.get_state_from(self._trigger_minion,'runSignal')
            if self.watch_state('runSignal', runSignal):
                self._running_protocol = runSignal
                if self._running_protocol:
                    self._start_protocol()
                    return True
                else:  # if self._running_protocol has been switched off, return False to stop protocal running and reset related params
                    self._end_protocol()
                    return False
            else:
                return self._running_protocol
        else:
            return False

    def _start_protocol(self):
        self.info('Starting protocol')
        self.set_streaming_state('protocolFn', self._protocolFn)
        self._protocol_start_time = self.get_timestamp()
        self.set_streaming_state('cmd_idx', 0)
        self.reset_servo_status()

    def _run_protocol(self):
        self._running_time = self.get_timestamp() - self._protocol_start_time
        cmd_idx = sum(self._running_time >= self._time_index_col) - 1
        if self.watch_state('cmd_idx', cmd_idx):
            for k, v in self._cmd_idx_lookup_table.items():
                if 'servo' in k:
                    # write serial command to set servo position
                    target_pos = int(self._protocol.iloc[cmd_idx, v[1]])
                    self.set_servo_motor_pos(k, v, target_pos)
                elif 'stepper' in k:
                    target_pos = self._protocol.iloc[cmd_idx, v[1]]
                    self.set_stepper_motor_pos(k, v, target_pos)
                elif 'pin' in k:
                    pin_num = v[0]
                    pin_val = self._protocol.iloc[cmd_idx, v[1]]
                    if pin_num < 10:
                        self._port.write(f'pin0{pin_num}{pin_val}\n'.encode())
                    else:
                        self._port.write(f'pin{pin_num}{pin_val}\n'.encode())
                    self.set_streaming_state(k, pin_val)

            self.set_streaming_state('cmd_idx', cmd_idx)
            if cmd_idx >= len(self._time_index_col) - 1:
                self._end_protocol()

    def _end_protocol(self):
        if self._cmd_idx_lookup_table is not None:
            pin_param = []
            flag_param = []
            servo_param = []
            stepper_param = []
            mask_param = []
            for k, v in self._cmd_idx_lookup_table.items():
                if 'servo' in k:
                    # write serial command to set servo position
                    if 'flag' in k:
                        flag_param = [k,v,180]
                    else:
                        servo_param.append([k,v,self.RADIUS_SERVO_MIN])
                elif 'stepper' in k:
                    stepper_param.append([k,v,0])
                elif 'pin' in k:
                    pin_num = v[0]
                    if pin_num < 10:
                        pin_param.append([k,f'pin0{pin_num}0\n'.encode()])
                    else:
                        pin_param.append([k,f'pin{pin_num}0\n'.encode()])
                elif 'mask' in k:
                    mask_param.append([k, f'm1{self.MASK_OFF_ANGLE[0]}\n'.encode()])
                    mask_param.append([k, f'm2{self.MASK_OFF_ANGLE[1]}\n'.encode()])

            if pin_param != []:
                for i in pin_param:
                    self._port.write(i[1])
                    self.set_streaming_state(i[0], 0)
            if flag_param != []:
                self.set_servo_motor_pos(*flag_param)
            if servo_param != []:
                for i in servo_param:
                    self.set_servo_motor_pos(*i)
            if stepper_param != []:
                for i in stepper_param:
                    self.set_stepper_motor_pos(*i)
            if mask_param != []:
                for i in mask_param:
                    self._port.write(i[1])
                    self.set_streaming_state(i[0], 0)
                self._mask_status = np.array([False, False])

        self._protocol_start_time = None
        self.set_streaming_state('cmd_idx', -1)
        self.set_state_to(self._trigger_minion, 'runSignal', False)
        self._running_time = 0
        self.info('Protocol ended')

    def set_servo_motor_pos(self, servo_name, servo_vals, target_pos):
        self._set_servo_motor_pos(servo_vals[0], target_pos)
        self.set_streaming_state(servo_name, target_pos)

    def _set_servo_motor_pos(self, servo_idx, target_pos):
        if servo_idx == self._motor_dict['radius_servo']:
            if target_pos < self.RADIUS_SERVO_MIN:
                self.warning(f"Radius servo position is smaller than the lower limit ({target_pos}<{self.RADIUS_SERVO_MIN})")
                target_pos = self.RADIUS_SERVO_MIN
        self._port.write(f's{servo_idx}{target_pos}\n'.encode())

    def set_stepper_motor_pos(self, stepper_name, stepper_vals, target_pos):
        has_set = self._set_stepper_motor_pos(stepper_vals[0], target_pos)
        if has_set:
            self.set_streaming_state(stepper_name, target_pos)

    def _set_stepper_motor_pos(self, stepper_idx, target_pos):
       if target_pos > 180 or target_pos < 0:
           self.error('Stepper position must be between 0 and 180 degrees')
           return False
       else:
           target_step = int(target_pos / 180 * self.STEPPER_180)
           delta_steps = target_step - self._stepper_counter
           if delta_steps > 0:
               self._port.write(f'f{stepper_idx}{delta_steps}\n'.encode())
           elif delta_steps < 0:
               self._port.write(f'b{stepper_idx}{-delta_steps}\n'.encode())
           self._stepper_counter = target_step
           return True

    def toggle_mask_servo(self, mask_num):
        self._toggle_mask_servo(mask_num)

    def _toggle_mask_servo(self, mask_num):
        # mask num is 0(left) or 1(right)
        if mask_num in [0,1]:
            if self._mask_status[mask_num]:
                self._mask_status[mask_num] = False
                self._port.write(f'm{mask_num+1}{self.MASK_OFF_ANGLE[mask_num]}\n'.encode())
            else:
                self._mask_status[mask_num] = True
                if self._mask_status[1 -mask_num]:
                    self._port.write(f'm{2-mask_num}{self.MASK_OFF_ANGLE[1-mask_num]}\n'.encode())
                    self._mask_status[1-mask_num] = False
                self._port.write(f'm{mask_num+1}{self.MASK_ON_ANGLE[mask_num]}\n'.encode())

    def reset_mask_servo(self):
        # mask num is 0(left) or 1(right)
        for i in range(2):
            self._mask_status[i] = False
            self._port.write(f'm{i+1}{self.MASK_OFF_ANGLE[i]}\n'.encode())


class ArduinoCompiler(AbstractCompiler):

    def __init__(self, *args, port_name='COM7', pin_address={}, **kwargs):
        super(ArduinoCompiler, self).__init__(*args, **kwargs)
        self._port_name = port_name
        self.pin_address = pin_address
        self._port = None
        self.input_pin_dict = {}
        self.output_pin_dict = {}

        try:
            self._port = fmt.Arduino(self._port_name)
            self._watching_state = {}
            for n, v in self.pin_address.items():
                if v.split(":")[-1] == 'i':
                    try:
                        self.input_pin_dict[n] = self._port.get_pin(v)
                        self.create_state(n, self.input_pin_dict[n].read())
                    except:
                        print(traceback.format_exc())
                elif v.split(":")[-1] == 'o':
                    try:
                        self.output_pin_dict[n] = self._port.get_pin(v)
                        self.create_state(n, 0)
                    except:
                        print(traceback.format_exc())
        except:
            print(traceback.format_exc())

    def on_time(self, t):
        # while self._port.bytes_available():
        #     self._port.iterate()
        for n, v in self.input_pin_dict.items():
            state = v.read()
            if self.watch_state(n, state) and state is not None:
                self.set_state(n,state)

        for n, v in self.output_pin_dict.items():
            state = self.get_state(n)
            if self.watch_state(n, state) and state is not None:
                v.write(state)

    def on_close(self):
        self.set_state('status', -1)
        self._port.exit()

class OMSInterface(StreamingCompiler):

    def __init__(self, *args, VID=None, PID=None, timeout=1, mw_size=1, **kwargs):
        super(OMSInterface, self).__init__(*args, **kwargs)
        if VID is None or PID is None:
            raise ValueError('VID and PID must be set')
        else:
            self._VID = VID
            self._PID = PID

        self.device = usb.core.find(idVendor=self._VID, idProduct=self._PID)
        if self.device is not None:
            self.device.set_configuration()
            self._endpoint = self.device[0][(0,0)][0]
        else:
            raise ValueError(f'Device not found. VID: {self._VID}, PID: {self._PID}')

        self._timeout = timeout
        self._mw_size = mw_size
        self._pos_buffer = np.zeros((self._mw_size, 2))

        self.create_streaming_state('xPos',0, shared=True, use_buffer=False)
        self.create_streaming_state('yPos',0, shared=True, use_buffer=False)
        # self.create_state('xPos', 0)
        # self.create_state('yPos', 0)

    def on_time(self, t):
        try:
            x, y = self._read_device()
            if x is not None and y is not None:
                self._pos_buffer = np.roll(self._pos_buffer, -1, axis=0)
                self._pos_buffer[-1, 0] = x
                self._pos_buffer[-1, 1] = y
                xPos,yPos = np.nanmean(self._pos_buffer, axis=0)

                self.set_streaming_state('xPos', xPos)
                self.set_streaming_state('yPos', yPos)
        except:
            print(traceback.format_exc())

        super().on_time(t)

    def _read_device(self):
        try:
            data = self.device.read(self._endpoint.bEndpointAddress, self._endpoint.wMaxPacketSize, self._timeout)
            if data is not None:
                x = data[2]
                y = data[4]
                if x > 127:
                    x = (x - 256)/128
                else:
                    x = (x+1)/128
                if y > 127:
                    y = (y - 256)/128
                else:
                    y = (y+1)/128
                return x, y
        except:
            self.debug('OMS device timeout')
            return None, None

    def on_close(self):
        self.set_state('status', -1)