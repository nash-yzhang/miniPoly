from apps.TISCam_compiler.app_bin import *
from bin.widgets.cameras import TisCamApp
from bin.minion import LoggerMinion

if __name__ == '__main__':
    Cam = TisCamApp('Tiscam_1', save_option='movie', refresh_interval=10)
    Cam2 = TisCamApp('Tiscam_2', save_option='movie', refresh_interval=10)
    GUI = CameraInterface('GUI', refresh_interval=5)
    logger = LoggerMinion('TestCam logger')
    logger.set_level('DEBUG')

    Cam.connect(GUI)
    Cam2.connect(GUI)

    Cam.attach_logger(logger)
    Cam2.attach_logger(logger)
    GUI.attach_logger(logger)

    logger.run()
    Cam.run()
    Cam2.run()
    GUI.run()
