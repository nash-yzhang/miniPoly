from apps.CaImg_App.app_bin import *
from bin.app.prototypes import AbstractGUIAPP, AbstractAPP, StreamingAPP, LoggerMinion
from bin.compiler import TISCameraCompiler, OMSInterface, MotorShieldCompiler

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
    Cam = StreamingAPP('Cam1', TISCameraCompiler, timer_minion='SCAN', trigger_minion='GUI',
                       save_option='movie', refresh_interval=10)

    Cam2 = StreamingAPP('Cam2', TISCameraCompiler, timer_minion='SCAN', trigger_minion='GUI',
                        save_option='movie', refresh_interval=10)

    Cam3 = StreamingAPP('Cam3', TISCameraCompiler, timer_minion='SCAN', trigger_minion='GUI',
                        save_option='movie', refresh_interval=10)

    Cam4 = StreamingAPP('Cam4', TISCameraCompiler, timer_minion='SCAN', trigger_minion='GUI',
                        save_option='movie', refresh_interval=10)

    OMS = StreamingAPP('OMS', OMSInterface, timer_minion='SCAN', trigger_minion='GUI',
                       refresh_interval=1, VID=VENDOR_ID, PID=PRODUCT_ID, mw_size=5)

    STIM = StreamingAPP('SERVO', MotorShieldCompiler, timer_minion='SCAN', trigger_minion='GUI',
                        refresh_interval=1, port_name='COM16',
                        motor_dict={'radius_servo': 1,
                                    'flag_servo':2,
                                    'azimuth_stepper': 1,
                                    'light_pin':8})

    DW = AbstractAPP('DATAWRAPPER', DataWrapper, trigger_minion='GUI',
                      remote_IP_address="192.168.233.66", remote_dir='D:\\data\\',
                      netdrive_dir="\\\\nas3\\datastore_bonhoeffer_group$\\Yue Zhang\\CaData\\")


    Cam.connect(SCAN)
    Cam.connect(GUI)
    Cam2.connect(SCAN)
    Cam2.connect(GUI)
    Cam3.connect(SCAN)
    Cam3.connect(GUI)
    Cam4.connect(SCAN)
    Cam4.connect(GUI)

    OMS.connect(SCAN)
    OMS.connect(GUI)

    STIM.connect(SCAN)
    STIM.connect(GUI)

    DW.connect(GUI)

    GUI.attach_logger(logger)
    DW.attach_logger(logger)
    SCAN.attach_logger(logger)
    Cam.attach_logger(logger)
    Cam2.attach_logger(logger)
    Cam3.attach_logger(logger)
    Cam4.attach_logger(logger)
    OMS.attach_logger(logger)
    STIM.attach_logger(logger)

    logger.run()
    GUI.run()
    SCAN.run()
    OMS.run()
    STIM.run()
    DW.run()
    Cam.run()
    Cam2.run()
    Cam3.run()
    Cam4.run()
