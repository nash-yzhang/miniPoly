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
        # self._params = {"CameraName": None, 'VideoFormat': None, 'SaveDir': None, 'SaveName': None,
        #                 'StreamToDisk': False, 'InitTime': 0., 'FrameCount': int(0), 'FrameTime': 0.}
        self.streaming = False
        self._BIN_FileHandle = None
        # self._AUX_FileHandle = None
        # self._AUX_writer = None
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
        video_format = self._params['VideoFormat']
        if self.camera.IsDevValid():
            self.camera.StopLive()
        self.camera.SetVideoFormat(self._params['VideoFormat'])
        self.camera.SetFormat(tis.SinkFormats(0))
        buffer_name = f"frame_{self._params['VideoFormat']}".replace(' ', '_')
        self.camera.SetContinuousMode(0)
        self.camera.StartLive(0)
        self.camera.SnapImage()
        frame = self.camera.GetImage()

        self.frame_shape = frame.shape
        if self.has_state(buffer_name):
            self.set_streaming_buffer(buffer_name, frame)
        else:
            self.create_streaming_buffer(buffer_name, frame, saving_opt=self.save_option, shared=True)
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
        self.set_streaming_buffer(self._buffer_name, frame)
        if self.streaming:
            self.set_streaming_state('FrameCount', self.get_streaming_state('FrameCount') + 1)
        else:
            self.set_streaming_state('FrameCount', 0)

    # def _data_streaming(self, frame_time, frame):
    #     if self.streaming:
    #         frame_time = frame_time - self._stream_init_time
    #         # Write to AUX file
    #         n_frame = self._n_frame_streamed
    #         self._AUX_writer.writerow([n_frame, frame_time])
    #
    #         if self.save_option == 'binary':
    #             # Write to BIN file
    #             self._BIN_FileHandle.write(bytearray(frame))
    #         elif self.save_option == 'movie':
    #             # Write to movie file
    #             self._BIN_FileHandle.write(frame.repeat(3,axis=2))
    #
    #         self._n_frame_streamed += 1
    #         self.set_state('FrameCount', self._n_frame_streamed)

    # def _streaming_setup(self):
    #     if_streaming = self.get_state('StreamToDisk')
    #     if self.watch_state('StreamToDisk', if_streaming):  # Triggered at the onset and the end of streaming
    #         if if_streaming:
    #             self._start_streaming()
    #         else:  # close all files before streaming stops
    #             self._stop_streaming()
    #
    # def _start_streaming(self):
    #     save_dir = self.get_state('SaveDir')
    #     file_name = self.get_state('SaveName')
    #     init_time = self.get_state('InitTime')
    #     if save_dir is None or file_name is None or init_time is None:
    #         self.error("Please set the save directory, file name and initial time before streaming.")
    #     else:
    #         if os.path.isdir(save_dir):
    #             if self.save_option == 'binary':
    #                 BIN_Fn = f"{self._camera_name}_{file_name}_{self.BINFile_Postfix}.miniPoly"
    #                 BIN_Fulldir = os.path.join(save_dir, BIN_Fn)
    #             elif self.save_option == 'movie':
    #                 BIN_Fn = f"{self._camera_name}_{file_name}_{self.BINFile_Postfix}.avi"
    #                 BIN_Fulldir = os.path.join(save_dir, BIN_Fn)
    #             AUX_Fn = f"{self._camera_name}_{file_name}_{self.AUXile_Postfix}.csv"
    #             AUX_Fulldir = os.path.join(save_dir, AUX_Fn)
    #             if os.path.isfile(BIN_Fulldir) or os.path.isfile(AUX_Fulldir):
    #                 self.error(f"File {BIN_Fn} or {AUX_Fn} already exists in the folder {save_dir}. Please change "
    #                            f"the save_name.")
    #             else:
    #                 if self.save_option == 'binary':
    #                     self._BIN_FileHandle = open(BIN_Fulldir, 'wb')
    #                 elif self.save_option == 'movie':
    #                     self._BIN_FileHandle = cv2.VideoWriter(BIN_Fulldir, cv2.VideoWriter_fourcc(*'MJPG'),
    #                                                            int(self.frame_rate),
    #                                                            (self.frame_shape[1], self.frame_shape[0]))
    #
    #                 self._AUX_FileHandle = open(AUX_Fulldir, 'w', newline='')
    #                 self._AUX_writer = csv.writer(self._AUX_FileHandle)
    #                 self._stream_init_time = init_time
    #                 self._n_frame_streamed = 0
    #                 self.streaming = True
    #
    # def _stop_streaming(self):
    #     if self._BIN_FileHandle is not None:
    #         if self.save_option == 'binary':
    #             self._BIN_FileHandle.close()
    #         elif self.save_option == 'movie':
    #             self._BIN_FileHandle.release()
    #     if self._AUX_FileHandle is not None:
    #         self._AUX_FileHandle.close()
    #     self._AUX_writer = None
    #     self._stream_init_time = None
    #     self._n_frame_streamed = None
    #     self.streaming = False

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


# class PCOCameraCompiler(AbstractCompiler):
#     TIS_DLL_DIR = "../miniPoly/tisgrabber/tisgrabber_x64.dll"
#     TIS_Width = ctypes.c_long()
#     TIS_Height = ctypes.c_long()
#     TIS_BitsPerPixel = ctypes.c_int()
#     TIS_colorformat = ctypes.c_int()
#
#     BINFile_Postfix = "PCO_IMG"
#
#     def __init__(self, *args, camera_name=None, save_option='binary', **kwargs):
#         super(PCOCameraCompiler, self).__init__(*args, **kwargs)
#
#         self.frame_rate = 1000 / self.refresh_interval
#         self._camera_name = camera_name
#         self._buffer_name = None
#         self._buf_img = None
#         self.frame_shape = None
#         self._params = {"CameraName": None, 'VideoFormat': None,
#                         'StreamToDisk': False, 'SaveDir': None, 'SaveName': None, 'InitTime': None,
#                         'FrameCount': 0, 'FrameTime': 0}
#         self.streaming = False
#         self._BIN_FileHandle = None
#         self._stream_init_time = None
#         self._n_frame_streamed = None
#
#         if save_option in ['binary', 'movie','tiff']:
#             self.save_option = save_option
#         else:
#             raise ValueError("save_option must be either 'binary', 'tiff', 'movie'")
#
#         for k, v in self._params.items():
#             self.create_state(k, v)
#         self._init_camera()
#
#     def _init_camera(self):
#         self.info("Searching camera...")
#         while self._params['CameraName'] is None:
#             self._params['CameraName'] = self.get_state('CameraName')
#         self.info(f"Camera {self._params['CameraName']} found")
#         self.camera = pco.Camera()
#         self.camera.record(number_of_images=5,mode='fifo')
#         self.camera.wait_for_first_image()
#         # self.camera.set_exposure_time(self.refresh_interval)
#         self.update_video_format()
#         self.watch_state('CameraName', self._params['CameraName'])
#         self.info(f"Camera {self._params['CameraName']} initialized")
#
#     def update_video_format(self):
#         buffer_name = "frame_PCO_cam"
#         self.info('Request ignored because updating video format is not available for PCO camera')
#         frame,meta = self.camera.image()
#         self.frame_shape = frame.shape
#         if self.has_state(buffer_name):
#             self.set_state(buffer_name, frame)
#         else:
#             self.create_state(buffer_name, frame, use_buffer=True)
#         self._buffer_name = buffer_name
#
#     def on_time(self, t):
#         try:
#             cameraName = self.get_state('CameraName')
#             if self.watch_state('CameraName', cameraName):
#                 if cameraName is not None:
#                     self._init_camera()
#                 else:
#                     try:
#                         self.disconnect_camera()
#                         self.info("Camera disconnected")
#                     except:
#                         self.error("An error occurred while disconnecting the camera")
#                         self.debug(traceback.format_exc())
#             else:
#                 self.process_frame()
#         except:
#             self.error("An error occurred while updating the camera")
#             self.error(traceback.format_exc())
#
#     def process_frame(self):
#         self._streaming_setup()
#         self.camera.wait_for_first_image()
#         frame, meta = self.camera.image(0xFFFFFFFF)
#         frame_time = time.perf_counter()
#         self.set_state(self._buffer_name, frame)
#         self._data_streaming(frame_time, frame)
#
#     def _data_streaming(self, frame_time, frame):
#         if self.streaming:
#             frame_time = frame_time - self._stream_init_time
#             # Write to AUX file
#             n_frame = self._n_frame_streamed
#
#             if self.save_option == 'binary':
#                 # Write to BIN file
#                 self._BIN_FileHandle.write(bytearray(frame))
#             elif self.save_option == 'movie':
#                 # Write to movie file
#                 frame = frame.astype(float)
#                 frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
#                 self._BIN_FileHandle.write(frame, compression='PNG')
#             elif self.save_option == 'tiff':
#                 self._BIN_FileHandle.save(frame)
#
#             self._n_frame_streamed += 1
#             self.set_state('FrameCount', self._n_frame_streamed)
#
#     def _streaming_setup(self):
#         if_streaming = self.get_state('StreamToDisk')
#         if self.watch_state('StreamToDisk', if_streaming):  # Triggered at the onset and the end of streaming
#             if if_streaming:
#                 self._start_streaming()
#             else:  # close all files before streaming stops
#                 self._stop_streaming()
#
#     def _start_streaming(self):
#         save_dir = self.get_state('SaveDir')
#         file_name = self.get_state('SaveName')
#         init_time = self.get_state('InitTime')
#         if save_dir is None or file_name is None or init_time is None:
#             self.error("Please set the save directory, file name and initial time before streaming.")
#         else:
#             if os.path.isdir(save_dir):
#                 if self.save_option == 'binary':
#                     BIN_Fn = f"{self._camera_name}_{file_name}_{self.BINFile_Postfix}.bin"
#                     BIN_Fulldir = os.path.join(save_dir, BIN_Fn)
#                 elif self.save_option == 'movie':
#                     BIN_Fn = f"{self._camera_name}_{file_name}_{self.BINFile_Postfix}.avi"
#                     BIN_Fulldir = os.path.join(save_dir, BIN_Fn)
#                 elif self.save_option == 'tiff':
#                     BIN_Fn = f"{self._camera_name}_{file_name}_{self.BINFile_Postfix}.tiff"
#                     BIN_Fulldir = os.path.join(save_dir, BIN_Fn)
#
#                 if os.path.isfile(BIN_Fulldir):
#                     self.error(f"File {BIN_Fn} already exists in the folder {save_dir}. Please change "
#                                f"the save_name.")
#                 else:
#                     if self.save_option == 'binary':
#                         self._BIN_FileHandle = open(BIN_Fulldir, 'wb')
#                     elif self.save_option == 'movie':
#                         self._BIN_FileHandle = cv2.VideoWriter(BIN_Fulldir, cv2.VideoWriter_fourcc(*'MJPG'),
#                                                                int(self.frame_rate),
#                                                                (self.frame_shape[1], self.frame_shape[0]))
#                     elif self.save_option == 'tiff':
#                         self._BIN_FileHandle = tifffile.TiffWriter(BIN_Fulldir, bigtiff=True)
#
#
#                     self._stream_init_time = init_time
#                     self._n_frame_streamed = 0
#                     self.streaming = True
#
#     def _stop_streaming(self):
#         if self._BIN_FileHandle is not None:
#             if self.save_option in ['binary','tiff']:
#                 self._BIN_FileHandle.close()
#             elif self.save_option == 'movie':
#                 self._BIN_FileHandle.release()
#
#         self._stream_init_time = None
#         self._n_frame_streamed = None
#         self.streaming = False
#
#     def disconnect_camera(self):
#         self.camera.stop()
#         self.camera.close()
#         self._params = {"CameraName": None, 'VideoFormat': None,
#                         'Trigger': 0, 'FrameCount': 0, 'FrameTime': 0}
#
#     def on_close(self):
#         self.camera.stop()
#         self.camera.close()
