from apps.TISCam_compiler.app_bin import CameraInterface
from bin.compiler import TISCameraDriver
from bin.minion import LoggerMinion
from time import sleep

if __name__ == '__main__':
    Cam = TISCameraDriver('Tiscam_1', refresh_interval=10)
    GUI = CameraInterface('GUI', refresh_interval=5)
    logger = LoggerMinion('TestCam logger')
    Cam.connect(GUI)
    Cam.attach_logger(logger)
    GUI.attach_logger(logger)
    logger.run()
    Cam.run()
    sleep(2)
    GUI.run()
