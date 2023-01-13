from bin.compiler import PololuServoDriver, ArduinoDriver
from bin.minion import LoggerMinion
from app import ServoCompilerGUI

if __name__ == '__main__':
    GUI = ServoCompilerGUI('GUI', interval=1)
    pololu_servo = PololuServoDriver('Pololu', interval=1, port_name='COM6',
                                     servo_dict={'yaw': 0, 'radius': 1, 'flagging': 5, })
    pololu_servo.connect(GUI)
    arduino_board = ArduinoDriver('Arduino', interval=1, port_name='COM7',
                                  pin_address={'LED1': 'd:8:o'})
    arduino_board.connect(GUI)
    logger = LoggerMinion('Logger')
    GUI.attach_logger(logger)
    pololu_servo.attach_logger(logger)
    arduino_board.attach_logger(logger)
    logger.run()
    arduino_board.run()
    pololu_servo.run()
    GUI.run()
