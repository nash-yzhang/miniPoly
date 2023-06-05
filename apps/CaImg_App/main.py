from apps.CaImg_App.app_bin import OMSInterfaceApp
from apps.CaImg_App.app_bin import *
from bin.widgets.cameras import TisCamApp
from bin.minion import LoggerMinion

VENDOR_ID = 0X046D
PRODUCT_ID = 0xC24E

if __name__ == '__main__':
    Cam = TisCamApp('Tiscam_1', save_option='movie', refresh_interval=10)
    GUI = MainGUIApp('GUI', refresh_interval=1, surveillance_state={'OMS': ['xPos', 'yPos']})
    OMS = OMSInterfaceApp('OMS', timer_minion='SCAN', trigger_minion='GUI', refresh_interval=1, VID=VENDOR_ID, PID=PRODUCT_ID, mw_size=5)
    # IO = DataIOApp('IO', timer_minion='SCAN', trigger_minion='GUI', state_dict={'OMS': ['xPos', 'yPos'],
    #                                                         'SERVO': ['yaw', 'radius'],
    #                                                         'SCAN': ['ca_frame_num']}, refresh_interval=1)
    SCAN = ScanListenerApp('SCAN',timer_minion='SCAN', trigger_minion='GUI', refresh_interval=1, port_name='COM6')
    # STIM = PololuServoApp('SERVO', timer_minion='SCAN', trigger_minion='GUI', refresh_interval=1, port_name='COM4', servo_dict={'yaw': 3, 'radius': 5})
    logger = LoggerMinion('LOGGER')
    logger.set_level('DEBUG')

    OMS.connect(SCAN)
    # STIM.connect(SCAN)
    Cam.connect(SCAN)

    SCAN.connect(GUI)
    OMS.connect(GUI)
    # STIM.connect(GUI)
    Cam.connect(GUI)
    #
    # IO.connect(GUI)
    # IO.connect(OMS)
    # IO.connect(STIM)
    # IO.connect(SCAN)
    #
    Cam.attach_logger(logger)
    GUI.attach_logger(logger)
    OMS.attach_logger(logger)
    SCAN.attach_logger(logger)
    # STIM.attach_logger(logger)
    # IO.attach_logger(logger)
    #
    logger.run()
    GUI.run()
    # IO.run()
    OMS.run()
    SCAN.run()
    # STIM.run()
    Cam.run()
