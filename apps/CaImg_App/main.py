from apps.CaImg_App.app_bin import OMSInterface
from apps.CaImg_App.app_bin import *
from bin.widgets.cameras import TisCamApp
from bin.minion import LoggerMinion

VENDOR_ID = 0X046D
PRODUCT_ID = 0xC24E

if __name__ == '__main__':
    Cam = TisCamApp('Tiscam_1', save_option='movie', refresh_interval=10)
    GUI = MainGUI('GUI', refresh_interval=1, surveillance_state={'OMS': ['xPos', 'yPos']})
    OMS = OMSInterface('OMS', refresh_interval=5, VID=VENDOR_ID, PID=PRODUCT_ID,mw_size=5)
    AUX = ArduinoInterface('AUX', refresh_interval=.2, port_name='COM6')
    STIM = PololuServoApp('SERVO', refresh_interval=.2, port_name='COM4', servo_dict={'yaw': 3, 'radius': 5})
    logger = LoggerMinion('LOGGER')
    logger.set_level('DEBUG')

    AUX.connect(GUI)
    OMS.connect(GUI)
    STIM.connect(GUI)
    Cam.connect(GUI)

    Cam.attach_logger(logger)
    GUI.attach_logger(logger)
    OMS.attach_logger(logger)
    AUX.attach_logger(logger)
    STIM.attach_logger(logger)

    logger.run()
    GUI.run()
    OMS.run()
    AUX.run()
    STIM.run()
    Cam.run()
