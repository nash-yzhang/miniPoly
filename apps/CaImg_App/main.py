from apps.CaImg_App.app_bin import OMSInterfaceApp
from apps.CaImg_App.app_bin import *
from bin.widgets.cameras import TisCamApp
from bin.minion import LoggerMinion

VENDOR_ID = 0X046D
PRODUCT_ID = 0xC24E

if __name__ == '__main__':
    Cam = TisCamApp('CAM1', save_option='movie', refresh_interval=10)
    GUI = MainGUIApp('GUI', refresh_interval=1, surveillance_state={'OMS': ['xPos', 'yPos']})
    OMS = OMSInterfaceApp('OMS', refresh_interval=1, VID=VENDOR_ID, PID=PRODUCT_ID, mw_size=5)
    IO = DataIOApp('IO', ts_minion_name='SCAN', state_dict={'OMS': ['xPos', 'yPos'],
                                                            'SERVO': ['yaw', 'radius'],
                                                            'SCAN': ['ca_frame_num'],
                                                            'CAM1':['FrameCount']}, refresh_interval=1)
    SCAN = ScanListenerApp('SCAN', refresh_interval=1, port_name='COM6')
    STIM = PololuServoApp('SERVO', refresh_interval=1, port_name='COM4', servo_dict={'yaw': 3, 'radius': 5})
    logger = LoggerMinion('LOGGER')
    logger.set_level('DEBUG')

    GUI.connect(SCAN)
    GUI.connect(OMS)
    GUI.connect(STIM)
    GUI.connect(Cam)
    #
    IO.connect(GUI)
    IO.connect(OMS)
    IO.connect(STIM)
    IO.connect(SCAN)
    IO.connect(Cam)
    #
    Cam.attach_logger(logger)
    GUI.attach_logger(logger)
    OMS.attach_logger(logger)
    SCAN.attach_logger(logger)
    STIM.attach_logger(logger)
    IO.attach_logger(logger)
    #
    logger.run()
    GUI.run()
    IO.run()
    OMS.run()
    SCAN.run()
    STIM.run()
    Cam.run()
