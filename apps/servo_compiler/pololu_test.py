from bin.compiler import PololuServoCompiler, ArduinoCompiler, SerialCommandCompiler
from bin.minion import LoggerMinion
from apps.servo_compiler.app_bin import ServoCompilerGUI

if __name__ == '__main__':
    GUI = ServoCompilerGUI('GUI', refresh_interval=1)
    pololu_servo = PololuServoCompiler('Pololu', refresh_interval=1, port_name='COM6',
                                       servo_dict={'yaw': 3, 'radius': 5, 'flagging': 1, })
    arduino_board = SerialCommandCompiler('Arduino', refresh_interval=1, port_name='COM7')
    logger = LoggerMinion('Logger')

    arduino_board.connect(GUI)
    pololu_servo.connect(GUI)

    pololu_servo.attach_logger(logger)
    arduino_board.attach_logger(logger)
    GUI.attach_logger(logger)

    logger.run()
    arduino_board.run()
    pololu_servo.run()
    GUI.run()
