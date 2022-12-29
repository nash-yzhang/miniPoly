from time import perf_counter, sleep


from bin.minion import BaseMinion, AbstractMinionMixin, TimerMinionMixin, TimerMinion
from definition import ROOT_DIR

import serial
import traceback

import PyQt5.QtWidgets as qw
import PyQt5.QtCore as qc
from PyQt5.Qt import Qt as qt
from PyQt5.QtGui import QIcon, QPixmap
from vispy import app, gloo


class AbstractCompiler(TimerMinionMixin):
    def __init__(self, processHandler, refresh_interval=10):
        super().__init__()
        self._processHandler = processHandler
        self._processHandler.add_callback('default', self.on_time)
        self._processHandler.interval = refresh_interval
        self._name = self._processHandler.name

    def on_time(self, t):
        self._processHandler.on_time(t)

    def on_protocol(self, t):
        pass


class QtCompiler(AbstractCompiler, qw.QMainWindow):

    def __init__(self, processHandler, refresh_interval=10, **kwargs):
        AbstractCompiler.__init__(self, processHandler, refresh_interval)
        qw.QMainWindow.__init__(self, **kwargs)
        self.setWindowTitle(self._name)
        self.setWindowIcon(QIcon(ROOT_DIR+'/bin/minipoly.ico'))
        self.renderSplashScreen()

    def renderSplashScreen(self):
        splash_pix = QPixmap(ROOT_DIR+'/bin/minipoly.ico')
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
        app.Canvas.__init__(self, *args, **kwargs)
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
            if i[2] not in ['u_resolution','u_time']:
                if type is not 'all':
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


class ServoDriver(TimerMinion):

    def initialize(self):
        super().initialize()
        self._port_name = 'COM6'
        self.servos = {'d:8:s': 1}

        try:
            self.init_polulo()
            self._watching_state = {}
            for n, v in self.servos.items():
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

    def on_time(self, t):
        try:
            for n, v in self.servos.items():
                state = self.get_state(n)
                if self.watch_state(n, state) and state is not None:
                    self.setTarget(v, int(state * 4000 + 4000))
                    # v.write(state*180)
        except:
            print(traceback.format_exc())

    def shutdown(self):
        self._port.close()

    def watch_state(self, name, val):
        if name not in self._watching_state.keys():
            self._watching_state[name] = val
            return True
        else:
            changed = val != self._watching_state[name]
            self._watching_state[name] = val
            return changed