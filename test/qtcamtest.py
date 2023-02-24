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
            self.refresh_interval = int(1/frame_rate)
        else:
            self.frame_rate = 1/self.refresh_interval
        self.name = None
        self.ic = None
        self._camera_name = camera_name
        self._video_format = video_format
        self._buf_img = None
        self._params = {"frame_rate": self.frame_rate, 'video_format': self._video_format, 'Gain': 0, 'Exposure': self.refresh_interval, 'Trigger': 0}
        for k, v in self._params.items():
            self.create_state(k, v)

    def initialize(self):
        super().initialize()
        print('Initializing TIS camera...')
        self._init_tisgrabber()
        print('Camera initialized.')
        if self._camera_name is None:
            self.hGrabber = self.ic.IC_ShowDeviceSelectionDialog(None)
            self.name = self.ic.IC_GetDeviceName(self.hGrabber)
        else:
            self.hGrabber = self.ic.IC_CreateGrabber()
            if not self.ic.IC_IsDevValid(self.hGrabber):
                all_device_name = [self.ic.IC_GetDeviceName(i) for i in range(self.ic.IC_GetDeviceCount())]
                raise FileNotFoundError(f"Device {self._camera_name} not found, the available devices are {all_device_name}.")
            else:
                self.name = self.ic.IC_GetDeviceName(self.hGrabber)
        if self._video_format is not None:
            try:
                self.ic.IC_SetVideoFormat(self.hGrabber, tis.T(self._video_format))
            except Exception:
                print(f"Video format {self._video_format} not found, using default format.")
        self.ic.IC_SetFrameRate(self.hGrabber, ctypes.c_float(self.frame_rate))
        self.ic.IC_SetContinuousMode(self.hGrabber, 1)
        # self.ic.IC_StartLive(self.hGrabber, 1)
        print(f"Camera {self.name} initialized.")

    def _init_tisgrabber(self):
        self.ic = ctypes.cdll.LoadLibrary(self.TIS_DLL_DIR)
        tis.declareFunctions(self.ic)
        self.ic.IC_InitLibrary(0)
        return self.ic

    def _snapImage(self):
        print('Snapping image...')
        snapped = self.ic.IC_SnapImage(self.hGrabber,2000)
        if snapped == tis.IC_SUCCESS:
            self._buf_img = self._getImage()

    def _getImage(self):

        # Query the values of image description
        self.ic.IC_GetImageDescription(self.hGrabber, self.TIS_Width, self.TIS_Height,
                                       self.TIS_BitsPerPixel, self.TIS_colorformat)

        # Calculate the buffer size
        bpp = int(self.TIS_BitsPerPixel.value / 8.0)
        buffer_size = self.TIS_Width.value * self.TIS_Height.value * self.TIS_BitsPerPixel.value

        # Get the image data
        imagePtr = self.ic.IC_GetImagePtr(self.hGrabber)

        imagedata = ctypes.cast(imagePtr,
                                ctypes.POINTER(ctypes.c_ubyte *
                                               buffer_size))

        # Create the numpy array
        image = np.ndarray(buffer=imagedata.contents,
                           dtype=np.uint8,
                           shape=(self.TIS_Height.value,
                                  self.TIS_Width.value,
                                  bpp))
        return image


    def on_time(self, t):
        print(f"Time: {t} (s)")
        try:
            self._snapImage()
            if self._buf_img is not None:
                cv2.imshow('image', self._buf_img)
            else:
                print("No image")
        except:
            print(traceback.format_exc())

    def shutdown(self):
        self.ic.IC_StopLive(self.hGrabber)
        self.ic.IC_ReleaseGrabber(self.hGrabber)
        self._port.close()

    def watch_state(self, name, val):
        if name not in self._watching_state.keys():
            self._watching_state[name] = val
            return True
        else:
            changed = val != self._watching_state[name]
            self._watching_state[name] = val
            return changed


if __name__ == '__main__':
    GUI = TISCamera('GUI',refresh_interval=1)
    logger = LoggerMinion('TestGUI logger')
    GUI.attach_logger(logger)
    logger.run()
    GUI.run()
