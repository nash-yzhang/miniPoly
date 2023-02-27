from apps.TISCam_compiler.app import TISCamera, CameraInterface
from bin.minion import LoggerMinion

if __name__ == '__main__':
    Cam = TISCamera('Tiscam_1', refresh_interval=1)
    GUI = CameraInterface('GUI', refresh_interval=1)
    logger = LoggerMinion('TestCam logger')
    Cam.connect(GUI)
    Cam.attach_logger(logger)
    GUI.attach_logger(logger)
    logger.run()
    Cam.run()
    GUI.run()
