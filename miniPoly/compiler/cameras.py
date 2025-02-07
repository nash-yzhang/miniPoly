import ctypes
import traceback

from miniPoly.compiler.prototypes import StreamingCompiler
from miniPoly.tisgrabber import tisgrabber as tis


class TISCameraCompiler(StreamingCompiler):
    TIS_DLL_DIR = "../tisgrabber/tisgrabber_x64.dll"
    TIS_Width = ctypes.c_long()
    TIS_Height = ctypes.c_long()
    TIS_BitsPerPixel = ctypes.c_int()
    TIS_colorformat = ctypes.c_int()

    BINFile_Postfix = "IC_IMG"
    AUXile_Postfix = "IC_AUX"

    def __init__(self, *args, camera_name=None, save_option='binary', **kwargs):
        super(TISCameraCompiler, self).__init__(*args, **kwargs)

        self.frame_rate = 1000 / self.refresh_interval
        self.ic = None
        self._camera_name = camera_name
        self._buffer_name = None
        self._buf_img = None
        self.frame_shape = None
        self._params = {"CameraName": None, 'VideoFormat': None, 'SaveDir': None, 'SaveName': None,
                        'StreamToDisk': False, 'InitTime': 0., 'FrameCount': int(0)}
        self.streaming = False
        self._BIN_FileHandle = None
        self._stream_init_time = None
        self._n_frame_streamed = None
        self.camera = None

        if save_option in ['binary', 'movie']:
            self.save_option = save_option
        else:
            raise ValueError("save_option must be either 'binary' or 'movie'")

        for k, v in self._params.items():
            if k == 'FrameCount':
                self.create_streaming_state(k, v, shared=False)
            else:
                self.create_state(k, v)
        self._init_camera()
        self.info(f"Camera {self.name} initialized.")

    def _init_camera(self):
        self.info("Searching camera...")

        while self._params['CameraName'] is None:
            self._params['CameraName'] = self.get_state('CameraName')
            if self.status() == -1:
                return None


        while self._params['VideoFormat'] is None:
            self._params['VideoFormat'] = self.get_state('VideoFormat')
            if self.status() == -1:
                return None

        self.info(f"Camera {self._params['CameraName']} found")
        self.camera = tis.TIS_CAM()
        self.camera.DevName = self._params['CameraName']
        if self.camera.IsDevValid():
            self.camera.StopLive()
        self.watch_state('CameraName', self.camera.DevName)
        self._camera_name = self.camera.DevName.replace(' ', '_')
        self.camera.open(self.camera.DevName)
        self.update_video_format()
        self.info(f"Camera {self._params['CameraName']} initialized")

    def update_video_format(self):
        if self.camera.IsDevValid():
            self.camera.StopLive()
        self.camera.SetVideoFormat(self._params['VideoFormat'])
        self.camera.SetFormat(tis.SinkFormats(0))
        buffer_name = f"frame_{self._params['VideoFormat']}".replace(' ', '_')
        self.camera.SetContinuousMode(0)
        self.camera.StartLive(0)
        self.camera.SetFrameRate(200)
        self.camera.SnapImage()
        frame = self.camera.GetImage()

        self.frame_shape = frame.shape
        if self.has_state(buffer_name):
            self.set_state(buffer_name, frame)
            self.set_streaming_buffer(buffer_name, frame)
        else:
            self.create_shared_buffer(buffer_name, frame)  # create a buffer for sharing only
            self.create_streaming_buffer(buffer_name, frame, saving_opt=self.save_option, shared=False) # create a buffer for streaming to local disk only
        self._buffer_name = buffer_name


    def on_time(self, t):
        try:
            cameraName = self.get_state('CameraName')
            if self.watch_state('CameraName', cameraName):
                if cameraName is not None:
                    self._init_camera()
                else:
                    try:
                        self.disconnect_camera()
                        self.info("Camera disconnected")
                    except:
                        self.error("An error occurred while disconnecting the camera")
                        self.debug(traceback.format_exc())
            else:
                self._params['VideoFormat'] = self.get_state('VideoFormat')
                if self.watch_state('VideoFormat', self._params['VideoFormat']):
                    self.update_video_format()
                if self.camera.IsDevValid():
                    self.process_frame()
        except:
            self.error("An error occurred while updating the camera")
            self.error(traceback.format_exc())

        super().on_time(t)

    def process_frame(self):
        self._streaming_setup()
        self.camera.SnapImage()
        frame = self.camera.GetImage()
        self.set_state(self._buffer_name, frame)
        self.set_streaming_buffer(self._buffer_name, frame)
        if self.streaming:
            self.set_streaming_state('FrameCount', self.get_streaming_state('FrameCount') + 1)
        else:
            self.set_streaming_state('FrameCount', 0)

    def should_stream(self):
        device_list = self.get_state_from(self._trigger_minion, 'StreamingDevices')
        if device_list is None:
            return False
        else:
            if self._params['CameraName'] in device_list:
                return True
            else:
                return False

    def disconnect_camera(self):
        self.camera.StopLive()
        self.camera = tis.TIS_CAM()
        self._params = {"CameraName": None, 'VideoFormat': None,
                        'Trigger': 0, 'FrameCount': 0, 'FrameTime': 0}

    def on_close(self):
        if self.camera is not None:
            if self.camera.IsDevValid():
                self.disconnect_camera()
                self.camera = None