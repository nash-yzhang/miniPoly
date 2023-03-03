from apps.TISCam_compiler.app_bin import *
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


class PololuServoApp(AbstractAPP):
    def __init__(self, *args, port_name='COM6', servo_dict={}, **kwargs):
        super(PololuServoApp, self).__init__(*args, **kwargs)
        self._param_to_compiler['port_name'] = port_name
        self._param_to_compiler['servo_dict'] = servo_dict

    def initialize(self):
        super().initialize()
        self._compiler = PololuServoCompiler(self, **self._param_to_compiler, )
        self.info("Pololu compiler initialized.")


class ArduinoApp(AbstractAPP):
    def __init__(self, *args, port_name='COM6', pin_address={}, **kwargs):
        super(ArduinoApp, self).__init__(*args, **kwargs)
        self._param_to_compiler['port_name'] = port_name
        self._param_to_compiler['pin_address'] = pin_address

    def initialize(self):
        super().initialize()
        self._compiler = ArduinoCompiler(self, **self._param_to_compiler, )
        self.info("Arduino Compiler initialized.")


if __name__ == '__main__':
    Cam = TisCamApp('Tiscam_1', save_option='movie', refresh_interval=10)
    GUI = CameraInterface('GUI', refresh_interval=5)
    pololu_servo = PololuServoApp('Servo_Pololu', refresh_interval=5, port_name='COM6',
                                       servo_dict={'yaw': 3, 'radius': 5, 'flagging': 1, })
    arduino_board = ArduinoApp('Serial_ArduinoNano', refresh_interval=1, port_name='COM7', pin_address={'LED1': 'd:8:o'})
    logger = LoggerMinion('TestCam logger')
    logger.set_level('DEBUG')

    Cam.connect(GUI)
    pololu_servo.connect(GUI)
    arduino_board.connect(GUI)

    Cam.attach_logger(logger)
    GUI.attach_logger(logger)
    pololu_servo.attach_logger(logger)
    arduino_board.attach_logger(logger)

    logger.run()
    arduino_board.run()
    pololu_servo.run()
    Cam.run()
    GUI.run()
