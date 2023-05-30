import csv
import os
import traceback
from time import perf_counter

import numpy as np
import pyfirmata2 as fmt
import serial
import usb.core
import usb.util

from bin.compiler.prototypes import AbstractCompiler


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

class OMSCompiler(AbstractCompiler):

    def __init__(self, *args, VID=None, PID=None, timeout=10, mw_size=1, **kwargs):
        super(OMSCompiler, self).__init__(*args, **kwargs)
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

        self.create_state('xPos', 0)
        self.create_state('yPos', 0)

    def on_time(self, t):
        try:
            x, y = self._read_device()
            if x is not None and y is not None:
                self._pos_buffer = np.roll(self._pos_buffer, -1, axis=0)
                self._pos_buffer[-1, 0] = x
                self._pos_buffer[-1, 1] = y
                xPos,yPos = np.nanmean(self._pos_buffer, axis=0)

                self.set_state('xPos', xPos)
                self.set_state('yPos', yPos)
        except:
            print(traceback.format_exc())

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