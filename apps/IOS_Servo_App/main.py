from apps.IOS_Servo_App.app_bin_TIS import *
from bin.minion import LoggerMinion
from time import sleep

class CameraInterface(AbstractGUIAPP):
    def __init__(self, *args, **kwargs):
        super(CameraInterface, self).__init__(*args, **kwargs)

    def initialize(self):
        super().initialize()
        self._win = CameraStimGUI(self)
        self.info("Camera Interface initialized.")
        self._win.show()


class TisCamApp(AbstractAPP):
    def __init__(self, *args, camera_name=None, save_option='binary', **kwargs):
        super(TisCamApp, self).__init__(*args, **kwargs)
        self._param_to_compiler['camera_name'] = camera_name
        self._param_to_compiler['save_option'] = save_option

    def initialize(self):
        super().initialize()
        self._compiler = TISCameraCompiler(self, **self._param_to_compiler, )
        self.info("Camera Interface initialized.")


class StimulusApp(AbstractAPP):
    def __init__(self, *args, servo_port_name, arduino_port_name, servo_dict, arduino_dict, **kwargs):
        super(StimulusApp, self).__init__(*args, **kwargs)
        self.name = 'Stimulus'
        self._param_to_compiler['servo_port_name'] = servo_port_name
        self._param_to_compiler['arduino_port_name'] = arduino_port_name
        self._param_to_compiler['servo_dict'] = servo_dict
        self._param_to_compiler['arduino_dict'] = arduino_dict

    def initialize(self):
        super().initialize()
        self._compiler = LightSaberStmulusCompiler(self, **self._param_to_compiler, )
        self.info("Stimulus compiler initialized.")

class IOApp(AbstractAPP):
    def __init__(self, *args, state_dict={}, buffer_dict={}, buffer_saving_opt={}, trigger=None, **kwargs):
        super(IOApp, self).__init__(*args, **kwargs)
        self.name = 'IO'
        self._param_to_compiler['state_dict'] = state_dict
        self._param_to_compiler['buffer_dict'] = buffer_dict
        self._param_to_compiler['buffer_saving_opt'] = buffer_saving_opt
        self._param_to_compiler['trigger'] = trigger

    def initialize(self):
        super().initialize()
        self._compiler = IOStreamingCompiler(self, **self._param_to_compiler, )
        self.info("IO compiler initialized.")

if __name__ == '__main__':
    Cam = TisCamApp('Tiscam_1', save_option='movie', refresh_interval=20)
    GUI = CameraInterface('GUI', refresh_interval=10)
    Stim = StimulusApp('Stimulus', servo_port_name='COM6', arduino_port_name='COM7',
                                       servo_dict={'yaw': 3, 'radius': 5, 'flagging': 1, },
                                       arduino_dict={'LED':'d:8:o'}, refresh_interval=5,)
    IO = IOApp('IO', refresh_interval=2, state_dict={'Tiscam_1':['FrameCount'],'Stimulus':['yaw', 'radius', 'flagging', 'LED']})
    logger = LoggerMinion('TestCam logger')
    logger.set_level('DEBUG')

    Cam.connect(GUI)
    Cam.connect(IO)
    Stim.connect(GUI)
    Stim.connect(IO)
    IO.connect(GUI)

    Cam.attach_logger(logger)
    GUI.attach_logger(logger)
    Stim.attach_logger(logger)
    IO.attach_logger(logger)

    logger.run()
    IO.run()
    Stim.run()
    Cam.run()
    GUI.run()