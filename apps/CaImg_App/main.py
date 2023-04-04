from apps.CaImg_App.app_bin import OMSInterface
from apps.CaImg_App.app_bin import *
from bin.widgets.cameras import TisCamApp
from bin.minion import LoggerMinion

VENDOR_ID = 0X046D
PRODUCT_ID = 0xC24E

if __name__ == '__main__':
    # Cam = TisCamApp('Tiscam_1', save_option='movie', refresh_interval=10)
    # Cam2 = TisCamApp('Tiscam_2', save_option='movie', refresh_interval=10)
    # OMS = OMSInterface('OMS', refresh_interval=5, VID=VENDOR_ID, PID=PRODUCT_ID,mw_size=5)
    # GUI = CameraInterface('GUI', refresh_interval=5, surveillance_state={'OMS': ['xPos', 'yPos']})
    GUI = CameraInterface('GUI', refresh_interval=5, surveillance_state={'Aux': ['mirPos','PEAK_mirPos']})
    Aux = ArduinoInterface('Aux', refresh_interval=1, port_name='COM21', pin_address={'mirPos': 'a:0:i'}, peak_detect_chn=['mirPos'])
    logger = LoggerMinion('TestCam logger')
    logger.set_level('DEBUG')

    Aux.connect(GUI)
    # Cam.connect(GUI)
    # Cam2.connect(GUI)
    # OMS.connect(GUI)
    #
    # Cam.attach_logger(logger)
    # Cam2.attach_logger(logger)
    # OMS.attach_logger(logger)
    GUI.attach_logger(logger)
    Aux.attach_logger(logger)

    logger.run()
    # OMS.run()
    # Cam.run()
    # Cam2.run()
    Aux.run()
    time.sleep(5)
    GUI.run()
