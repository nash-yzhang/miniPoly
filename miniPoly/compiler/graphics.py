import traceback
from time import sleep

import numpy as np
import pandas as pd
from PyQt5 import QtWidgets as qw, QtCore as qc
from PyQt5.QtGui import QIcon, QPixmap
from vispy import app, gloo

from miniPoly.compiler.prototypes import AbstractCompiler
from miniPoly.core.minion import AbstractMinionMixin, BaseMinion
from miniPoly.definition import ROOT_DIR
from miniPoly.compiler.prototypes import StreamingCompiler


class QtCompiler(AbstractCompiler, qw.QMainWindow):

    def __init__(self, processHandler, **kwargs):
        AbstractCompiler.__init__(self, processHandler)
        qw.QMainWindow.__init__(self, **kwargs)
        self.setWindowTitle(self.name)
        self.setWindowIcon(QIcon(ROOT_DIR + '/minipoly.ico'))
        self.renderSplashScreen()

    def renderSplashScreen(self):
        splash_pix = QPixmap(ROOT_DIR + '/minipoly.ico')
        splash = qw.QSplashScreen(splash_pix, qc.Qt.WindowStaysOnTopHint)
        # add fade to splashscreen
        splash.show()
        for i in range(20):
            splash.setWindowOpacity(1.5 - abs(1.5 - (i / 10)))
            sleep(0.03)
        splash.close()  # close the splash screen


class ShaderStreamer(app.Canvas, StreamingCompiler):
    _vpos = np.array([[-1, -1], [+1, -1], [-1, +1], [+1, +1]], dtype=np.float32)

    VS = """
    attribute vec2 a_position;
    varying vec2 v_position;
    void main (void) {
        gl_Position = vec4(a_position, 0.0, 1.0);
        v_position = a_position;
    }
    """

    def __init__(self, processHandler, *args, FSFn=None, fullscreen=False, timer_minion='SCAN', trigger_minion='GUI',
                 refresh_interval=1, **kwargs):
        super().__init__(*args, **kwargs)
        StreamingCompiler.__init__(self, processHandler, timer_minion=timer_minion,
                                   trigger_minion=trigger_minion)  # self.VS = None
        self.FS = None
        self.program = None

        if FSFn is not None:
            self._FSFn = FSFn
            self._init_program()
        else:
            self._FSFn = ''

        self.create_streaming_state('FSFn', self._FSFn, shared=False, use_buffer=False)
        self.watch_state('FSFn', self._FSFn)

        self.fullscreen = fullscreen
        self.watch_state('fullscreen', self.fullscreen)

        self._shared_uniform_states = []

        # Protocol execution related params
        self.watch_state('runSignal', False)  # create a runSignal watcher, runSignal is a shared state from GUI
        self._running_protocol = False

        self.create_streaming_state('protocolFn', '', shared=False, use_buffer=False)
        self.watch_state('protocolFn', '')

        # The following shared state are for debugging
        self.create_state('serial_cmd', '')
        self.watch_state('serial_cmd', '')

        self.watch_state('cmd_idx', -1)
        self.create_streaming_state('cmd_idx', -1, shared=True, use_buffer=True)
        self._protocolFn = ''
        self._protocol = None
        self._protocol_start_time = None
        self._time_index_col = None
        self._running_time = 0

    def load_shader_file(self, fn):
        with open(fn, 'r') as shaderfile:
            return (shaderfile.read())

    def load_FS(self, fn):
        try:
            FS = self.load_shader_file(fn)
            return FS
        except Exception:
            self.error(f'Error in loading vertex shader: {fn}\n{traceback.format_exc()}')
            return None

    def _init_program(self):
        self.FS = self.load_FS(self._FSFn)
        # if self.VS is not None and self.FS is not None:
        if self.FS is not None:
            self.program = gloo.Program(self.VS, self.FS)
            self.program['a_position'] = gloo.VertexBuffer(self._vpos)
            self.program['u_resolution'] = (self.size[0], self.size[1])
            self.program['u_time'] = 0
            rv, uv = self.check_variables()
            if uv:
                self.error(f'Found {len(uv)} unsettled variables: {uv}')
            if rv:
                self.warning(f'Found {len(rv)} pending variables: {rv}')
            self.create_shared_uniform_state(type='uniform')
        else:
            self.error(f'Rendering program has not been built!')

    def create_shared_uniform_state(self, type='uniform'):
        for i in self.program.variables:
            if i[2] not in ['u_resolution', 'u_time']:
                if type != 'all':
                    if i[0] == type:
                        try:
                            self.create_streaming_state(i[2], list(self.program[i[2]].astype(float)))
                        except KeyError:
                            self.warning(f'Uniform {i[2]} has not been set: {i[2]}\n{traceback.format_exc()}')
                            if i[1] == 'vec2':
                                self.create_streaming_state(i[2], [0, 0])
                            elif i[1] == 'vec3':
                                self.create_streaming_state(i[2], [0, 0, 0])
                            elif i[1] == 'vec4':
                                self.create_streaming_state(i[2], [0, 0, 0, 0])
                            else:
                                self.create_streaming_state(i[2], 0)
                        except:
                            self.error(f'Error in creating shared state for uniform: {i[2]}\n{traceback.format_exc()}')
                        self._shared_uniform_states.append(i[2])
                else:
                    if i[0] not in ['varying', 'constant']:
                        self.create_streaming_state(i[2], self.program[i[2]])
                        self._shared_uniform_states.append(i[2])

    def check_variables(self):
        redundant_variables = list(self.program._pending_variables.keys())
        unsettled_variables = []
        for i in self.program.variables:
            if i[0] not in ['varying', 'constant']:
                if i[2] not in self.program._user_variables.keys():
                    unsettled_variables.append(i[2])
        return redundant_variables, unsettled_variables

    def on_time(self, t):
        self.set_fullscreen()
        running = self.get_run_signal()
        if running:
            self._run_protocol()
        else:
            if self._protocol_start_time is not None:
                self._end_protocol()
        super().on_time(t)
        if self.program is not None:
            self.program['u_time'] = t
            self.update()

    def set_fullscreen(self):
        fullscreen = self.get_state_from(self._trigger_minion, 'fullscreen')
        if self.watch_state('fullscreen', fullscreen) and fullscreen is not None:
            self.fullscreen = fullscreen

    def on_draw(self, event):
        gloo.clear()
        if self.program is not None:
            self.program.draw('triangle_strip')

    def get_protocol_fn(self):
        if self._protocol_start_time is None:  # Only execute if protocol is not running
            protocolFn = self.get_state_from(self._trigger_minion, 'protocolFn')
            if self.watch_state('protocolFn', protocolFn) and protocolFn not in ['', None]:
                self.info(f"Loading protocol from {protocolFn}")
                self._protocol = pd.read_excel(protocolFn)
                self._protocolFn = protocolFn
                missing_uniforms = [k for k in self._shared_uniform_states if k not in self._protocol.columns]
                if len(missing_uniforms) > 0:
                    self.error(
                        f'Protocol cannot be executed because the following uniforms are missing in the protocol file: {missing_uniforms}')
                    self._protocol = None
                    self._protocolFn = None
                else:
                    self._time_index_col = self._protocol['time'].to_numpy()

    def get_FS(self):
        if self._protocol_start_time is None:  # Only execute if protocol is not running
            self._FSFn = self.get_state_from(self._trigger_minion, 'FSFn')
            if self.watch_state('FSFn', self._FSFn) and self._FSFn not in ['', None]:
                self.info(f"Loading shader from {self._FSFn}")
                self._init_program()
                self.info(f"Rendering program updated")

    def get_run_signal(self):
        self.get_FS()
        self.get_protocol_fn()
        if self._protocol is not None and self.FS is not None:  # Only execute if protocol and FS are loaded
            runSignal = self.get_state_from(self._trigger_minion, 'runSignal')
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
        self.set_streaming_state('FSFn', self._FSFn)
        self._protocol_start_time = self.get_timestamp()
        self.set_streaming_state('cmd_idx', 0)

    def _run_protocol(self):
        self._running_time = self.get_timestamp() - self._protocol_start_time
        cmd_idx = sum(self._running_time >= self._time_index_col) - 1
        if self.watch_state('cmd_idx', cmd_idx):
            cmd = self._protocol.iloc[cmd_idx, :]
            for k, v in cmd.items():
                self.update_stim_state(k, v)
            self.set_streaming_state('serial_cmd', cmd['serial_cmd'])

            self.set_streaming_state('cmd_idx', cmd_idx)
            if cmd_idx >= len(self._time_index_col) - 1:
                self._end_protocol()
            self.exec_stim_cmd()

    def exec_stim_cmd(self):
        self.update()

    def update_stim_state(self, k, v):
        if k in self._shared_uniform_states:
            self.program[k] = v
            self.set_streaming_state(k, v)

    def _end_protocol(self):
        gloo.clear('black')
        self.update()

        self._protocol_start_time = None
        self.FS = None
        self.set_streaming_state('cmd_idx', -1)
        self.set_state_to(self._trigger_minion, 'runSignal', False)
        self._running_time = 0
        self.info('Protocol ended')

    def on_resize(self, event):
        # Define how should be rendered image should be resized by changing window size
        gloo.set_viewport(0, 0, *self.physical_size)
        self.program['u_resolution'] = self.size

    def on_close(self):
        self.set_state('status', -1)
        self.close()


class GLCompiler(app.Canvas, AbstractMinionMixin):

    def __init__(self, processHandler, *args, protocol_commander: BaseMinion = None,
                 VS=None, FS=None, refresh_interval=10, **kwargs):
        super().__init__(*args, **kwargs)
        # processor.Canvas.__init__(self, *args, **kwargs)
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
