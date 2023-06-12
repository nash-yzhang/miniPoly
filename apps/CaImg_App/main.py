from apps.CaImg_App.app_bin import *
from bin.app.prototypes import AbstractGUIAPP, StreamingAPP, LoggerMinion
from bin.compiler import TISCameraCompiler, OMSInterface, PololuServoInterface

VENDOR_ID = 0X046D
PRODUCT_ID = 0xC24E

if __name__ == '__main__':
    # Set up logger for all minions
    logger = LoggerMinion('LOGGER')

    # Set up GUI as the trigger minion for Cam, SCAN and OMS
    GUI = AbstractGUIAPP('GUI', MainGUI, refresh_interval=1, surveillance_state={'OMS': ['xPos', 'yPos']})

    # Set up SCAN as the timer minion for Cam, OMS and IO, also it serves as the calcium frame counter
    SCAN = StreamingAPP('SCAN', ScanListener, timer_minion='SCAN', trigger_minion='GUI', refresh_interval=1, port_name='COM15')
    SCAN.connect(GUI)


    # Set up functional minion
    Cam = StreamingAPP('Cam1', TISCameraCompiler, timer_minion='SCAN', trigger_minion='GUI', save_option='movie', refresh_interval=10)
    OMS = StreamingAPP('OMS', OMSInterface, timer_minion='SCAN', trigger_minion='GUI', refresh_interval=1, VID=VENDOR_ID, PID=PRODUCT_ID, mw_size=5)
    STIM = StreamingAPP('SERVO', PololuServoInterface, timer_minion='SCAN', trigger_minion='GUI', refresh_interval=1, port_name='COM4', servo_dict={'yaw': (0, 2800, 7516), 'radius': (1, 2240, 10240)})


    Cam.connect(SCAN)
    Cam.connect(GUI)

    OMS.connect(SCAN)
    OMS.connect(GUI)

    STIM.connect(SCAN)
    STIM.connect(GUI)

    GUI.attach_logger(logger)
    SCAN.attach_logger(logger)
    Cam.attach_logger(logger)
    OMS.attach_logger(logger)
    STIM.attach_logger(logger)

    logger.run()
    GUI.run()
    SCAN.run()
    Cam.run()
    OMS.run()
    STIM.run()
