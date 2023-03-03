from apps.TISCam_compiler.app_bin import *
from bin.minion import LoggerMinion
from time import sleep

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
