import traceback
from time import sleep

from PyQt5 import QtWidgets as qw, QtCore as qc
from PyQt5.QtGui import QIcon, QPixmap
from vispy import app, gloo

from bin.compiler.prototypes import AbstractCompiler
from bin.minion import AbstractMinionMixin, BaseMinion
from definition import ROOT_DIR


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
            sleep(0.03)
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
