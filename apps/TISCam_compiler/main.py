from apps.CaImg_App.app_bin import *
from miniPoly.prototype.cameras import TisCamApp
from miniPoly.prototype.Logging import LoggerMinion

VENDOR_ID = 0X046D
PRODUCT_ID = 0xC24E

if __name__ == '__main__':
    Cam = TisCamApp('Tiscam_1', save_option='movie', refresh_interval=10)
    GUI = MainGUIApp('GUI', refresh_interval=5)
    OMS = OMSInterfaceApp('OMS', refresh_interval=5, VID = VENDOR_ID, PID = PRODUCT_ID)
    logger = LoggerMinion('TestCam logger')
    logger.set_level('DEBUG')

    Cam.connect(GUI)
    OMS.connect(GUI)

    Cam.attach_logger(logger)
    GUI.attach_logger(logger)
    OMS.attach_logger(logger)

    logger.run()
    OMS.run()
    Cam.run()
    GUI.run()
