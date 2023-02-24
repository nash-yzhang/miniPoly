from bin.compiler import PololuServoDriver, ArduinoDriver, SerialCommander
from bin.minion import LoggerMinion
from app import ServoCompilerGUI

if __name__ == '__main__':
    GUI = ServoCompilerGUI('GUI', refresh_interval=1)
    pololu_servo = PololuServoDriver('Pololu', refresh_interval=1, port_name='COM4',
                                     servo_dict={'yaw': 4, 'radius': 5, 'flagging': 3, })
    pololu_servo.connect(GUI)
    arduino_board = SerialCommander('Arduino', refresh_interval=1, port_name='COM6')
    # arduino_board = ArduinoDriver('Arduino', interval=1, port_name='COM3',
    #                               pin_address={'LED1': 'd:8:o'})
    arduino_board.connect(GUI)
    logger = LoggerMinion('Logger')
    GUI.attach_logger(logger)
    pololu_servo.attach_logger(logger)
    arduino_board.attach_logger(logger)
    logger.run()
    arduino_board.run()
    pololu_servo.run()
    GUI.run()