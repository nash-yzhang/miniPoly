import ctypes
import traceback
import numpy as np
import cv2
import PyQt5.QtWidgets as qw
import PyQt5.QtGui as qg

from bin.app import AbstractGUIAPP
from bin.compiler import QtCompiler
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
            self.frame_rate = 1000 / self.refresh_interval
        self.ic = None
        self._camera_name = camera_name
        self._buf_img = None
        self._params = {"CameraName":None, "FrameRate": self.frame_rate, 'VideoFormat': None, 'Gain': 0,
                        'Exposure': self.refresh_interval, 'Trigger': 0}

    def initialize(self):
        super().initialize()
        for k, v in self._params.items():
            self.create_state(k, v)
        print('Connecting camera...')
        while self._params['CameraName'] is None:
            self._params['CameraName'] = self.get_state('CameraName')
        self.camera = tis.TIS_CAM()
        self.camera.DevName = self._params['CameraName']
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


class CameraInterface(AbstractGUIAPP):
    def __init__(self, *args, **kwargs):
        super(CameraInterface, self).__init__(*args, **kwargs)

    def initialize(self):
        super().initialize()
        self._win = CameraGUI(self)
        self.info("Camera Interface initialized.")
        self._win.show()

class CameraGUI(QtCompiler):

    def __init__(self, *args, **kwargs):
        super(CameraGUI, self).__init__(*args, **kwargs)
        self._camera_minions = [i for i in self.get_linked_minion_names() if 'tiscam' in i.lower()]
        self._connected_camera_minions = {}

        self.layout = qw.QVBoxLayout()
        self._tiscamHandle = tis.TIS_CAM()

        # Create camera selection layout
        self.layout_camera_selection = qw.QHBoxLayout()

        # Create camera selection dropdown list
        self.camera_list = qw.QComboBox()
        self._deviceList = self._tiscamHandle.GetDevices()
        self.camera_list.addItems(['N/A'])
        self.camera_list.addItems([i.decode('utf-8') for i in self._deviceList])

        # Create connect button, connected to the current selected camera in the list
        self.button_connect = qw.QPushButton('Add')
        self.button_connect.clicked.connect(self.connect_camera)

        self.layout_camera_selection.addWidget(self.camera_list)
        self.layout_camera_selection.addWidget(self.button_connect)

        self.frameCanvas = qw.QLabel()
        self._frame = qg.QPixmap()
        self.frameCanvas.setPixmap(self._frame)
        self.layout.addWidget(self.frameCanvas)
        self.layout.addLayout(self.layout_camera_selection)
        self.main_widget = qw.QWidget()
        self.main_widget.setLayout(self.layout)
        self.setCentralWidget(self.main_widget)

    def on_time(self, t):
        for mi in self._connected_camera_minions.values():
            frame = self.get_buffer_from(mi, 'frame')
            if frame is not None:
                self._frame = qg.QPixmap.fromImage(qg.QImage(frame, frame.shape[1], frame.shape[0], frame.strides[0],
                                                             qg.QImage.Format_RGB888))
                self.frameCanvas.setPixmap(self._frame)
        self._processHandler.on_time(t)
    def connect_camera(self):
        for mi in self._camera_minions:
            camera_name = self.get_state_from(mi, 'CameraName')
            if camera_name is None:
                self.set_state_to(mi, 'CameraName', self.camera_list.currentText())
                self._connected_camera_minions[self.camera_list.currentText()] = mi
                break




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

# if __name__ == '__main__':
#     Cam = TISCamera('Cam', refresh_interval=1)
#     GUI = Reader('GUI', refresh_interval=1)
#     logger = LoggerMinion('TestCam logger')
#     Cam.connect(GUI)
#     Cam.attach_logger(logger)
#     GUI.attach_logger(logger)
#     logger.run()
#     Cam.run()
#     GUI.run()
