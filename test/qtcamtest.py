import ctypes
import traceback
import numpy as np
import cv2
from src.tisgrabber import tisgrabber as tis
from bin.minion import TimerMinion, LoggerMinion


class TISCamera(TimerMinion):
    TIS_DLL_DIR = "../src/tisgrabber/tisgrabber_x64.dll"
    TIS_Width = ctypes.c_long()
    TIS_Height = ctypes.c_long()
    TIS_BitsPerPixel = ctypes.c_int()
    TIS_colorformat = ctypes.c_int()

    def __init__(self, *args, camera_name=None, video_format=None, frame_rate=None, **kwargs):
        super(TISCamera, self).__init__(*args, **kwargs)
        if frame_rate is not None:
            self.refresh_interval = int(1 / frame_rate)
        else:
            self.frame_rate = 1 / self.refresh_interval
        self.ic = None
        self._camera_name = camera_name
        self._buf_img = None
        self._params = {"frame_rate": self.frame_rate, 'video_format': None, 'Gain': 0,
                        'Exposure': self.refresh_interval, 'Trigger': 0}
        for k, v in self._params.items():
            self.create_state(k, v)

    def initialize(self):
        super().initialize()
        print('Initializing TIS camera...')
        self.camera = tis.TIS_CAM()
        self.camera.DevName = self.camera.GetDevices()[0].decode("utf-8")
        self.camera.open(self.camera.DevName)
        self._camera_name = self.camera.DevName.replace(' ', '_')
        empty_buffer = np.zeros((self.camera.get_video_format_height(), self.camera.get_video_format_width(), 3),
                                dtype=np.uint8)
        self.create_shared_buffer("frame", empty_buffer, empty_buffer.nbytes)
        self.camera.SetContinuousMode(0)
        self.camera.StartLive(0)
        print(f"Camera {self.name} initialized.")

    def on_time(self, t):
        try:
            self.camera.SnapImage()
            self.set_foreign_buffer(self.name, 'frame', self.camera.GetImage())
        except:
            print(traceback.format_exc())

    def shutdown(self):
        self.camera.release()

    def watch_state(self, name, val):
        if name not in self._watching_state.keys():
            self._watching_state[name] = val
            return True
        else:
            changed = val != self._watching_state[name]
            self._watching_state[name] = val
            return changed


class Reader(TimerMinion):
    def __init__(self, *args, **kwargs):
        super(Reader, self).__init__(*args, **kwargs)

    def initialize(self):
        super().initialize()
        print('Initializing....')
        while 'b*Cam_frame' not in self._shared_dict.keys():
            self.link_foreign_buffer('Cam','frame')
    def on_time(self,t):
        try:
            cv2.imshow('Frame', self.get_foreign_buffer('Cam','frame'))
            cv2.waitKey(1)
        except:
            self.logger.error(traceback.format_exc())


if __name__ == '__main__':
    Cam = TISCamera('Cam', refresh_interval=1)
    GUI = Reader('GUI', refresh_interval=1)
    logger = LoggerMinion('TestCam logger')
    Cam.connect(GUI)
    Cam.attach_logger(logger)
    GUI.attach_logger(logger)
    logger.run()
    Cam.run()
    GUI.run()
