import ctypes
import time
import traceback

from bin.app import AbstractGUIAPP
from bin.compiler import QtCompiler
from src.tisgrabber import tisgrabber as tis
from bin.minion import TimerMinion, LoggerMinion

from apps.TISCam_compiler.compiler import CameraGUI

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
            self.frame_rate = 1000 / self.refresh_interval
        self.ic = None
        self._camera_name = camera_name
        self._buf_img = None
        self._params = {"CameraName":None, 'VideoFormat': None,
                        'ExposureTime': self.refresh_interval, 'FPS':0, 'Gain': 0,
                        'Trigger': 0, 'FrameCount':0, 'FrameTime':0}

    def initialize(self):
        super().initialize()
        for k, v in self._params.items():
            self.create_state(k, v)
        self._init_camera()
        self.info(f"Camera {self.name} initialized.")

    def _init_camera(self):
        self.info("Searching camera...")
        while self._params['CameraName'] is None:
            self._params['CameraName'] = self.get_state('CameraName')
        while self._params['VideoFormat'] is None:
            self._params['VideoFormat'] = self.get_state('VideoFormat')
        self.info(f"Camera {self._params['CameraName']} found")
        self.camera = tis.TIS_CAM()
        self.camera.DevName = self._params['CameraName']
        if self.camera.IsDevValid():
            self.camera.StopLive()
        self._camera_name = self.camera.DevName.replace(' ', '_')
        self.camera.open(self.camera.DevName)
        self.camera.SetVideoFormat(self._params['VideoFormat'])
        self.camera.SetContinuousMode(0)
        self.camera.StartLive(0)
        self.camera.SnapImage()
        frame = self.camera.GetImage()
        if self.has_buffer('frame'):
            if frame.shape == self.get_buffer('frame').shape:
                self.set_buffer('frame', frame)
            else:
                self._shared_buffer[f"{self.name}_frame"].close()
                time.sleep(0.1)
                self.create_shared_buffer("frame", frame, frame.nbytes)
                self.set_buffer('frame', self.camera.GetImage())
        else:
            self.create_shared_buffer("frame", frame, frame.nbytes)
        self.info(f"Camera {self._params['CameraName']} initialized")

    def on_time(self, t):
        try:
            if self.status <= 0:
                self.on_close()

            try:
                self.set_state('Gain', self.camera.GetPropertyValue('Gain', 'Value'))
            except:
                self.debug(traceback.format_exc())

            # cur_ft = [0]
            # err = self.camera.GetPropertyAbsoluteValue('Exposure', 'Value', cur_ft)
            # if err == 1:
            #     self.set_state('ExposureTime', cur_ft[0])
            #
            # if self.watch_state('Gain', self.get_state('Gain')):
            #     self.camera.SetPropertyValue('Gain', 'Value', self.get_state('Gain')+0)
            #
            # if self.watch_state('ExposureTime', self.get_state('ExposureTime')):
            #     self.camera.SetPropertyAbsoluteValue('Exposure', 'Value', self.get_state('ExposureTime')/1000)
            #
            cameraName = self.get_state('CameraName')
            if self.watch_state('CameraName', cameraName):
                if cameraName is not None:
                    self._init_camera()
                else:
                    try:
                        self.disconnect_camera()
                    except:
                        self.error("An error occurred while disconnecting the camera")
                        self.error(traceback.format_exc())
            else:
                if self.camera.IsDevValid():
                    self.camera.SnapImage()
                    self.set_buffer('frame', self.camera.GetImage())
        except:
            self.error(traceback.format_exc())

    def disconnect_camera(self):
        self.camera.StopLive()
        self.camera = tis.TIS_CAM()
        self._params = {"CameraName": None, 'VideoFormat': None,
                        'ExposureTime': self.refresh_interval, 'FPS': 0, 'Gain': 0,
                        'Trigger': 0, 'FrameCount': 0, 'FrameTime': 0}

    def on_close(self):
        if self.camera.IsDevValid():
            self.disconnect_camera()
        self.set_state('status', -1)

    def watch_state(self, name, val):
        if name not in self._watching_state.keys():
            self._watching_state[name] = val
            return True
        else:
            changed = val != self._watching_state[name]
            self._watching_state[name] = val
            return changed


class CameraInterface(AbstractGUIAPP):
    def __init__(self, *args, **kwargs):
        super(CameraInterface, self).__init__(*args, **kwargs)

    def initialize(self):
        super().initialize()
        self._win = CameraGUI(self)
        self.info("Camera Interface initialized.")
        self._win.show()

