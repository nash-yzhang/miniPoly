import numpy as np
from bin.gui import DataframeTable
from bin.compiler import QtCompiler
import PyQt5.QtWidgets as qw

import ctypes
from src.tisgrabber import tisgrabber as tis


class TISCamCommander(QtCompiler):
    def __init__(self, *args, windowSize=(900, 300), **kwargs):
        super().__init__(*args, **kwargs)
        self.add_timer('protocol_timer', self.on_protocol)
        self.create_state('is_running', False)

        self._timer_started = False
        self.timer_switcher = qw.QPushButton('Start')
        self.timer_switcher.clicked.connect(self.switch_timer)
        self.resize(*windowSize)

        self.layout = qw.QVBoxLayout()
        self.layout.addLayout(self.groupbox_layout)
        self.layout.addWidget(self.timer_switcher)

        self.main_widget = qw.QWidget()
        self.main_widget.setLayout(self.layout)
        self.setCentralWidget(self.main_widget)

        self._init_menu()

    def addTableBox(self, name):
        frame = qw.QGroupBox(self)
        frame.setTitle(name)
        table = DataframeTable(self.centralWidget())
        frame_layout = qw.QVBoxLayout()
        frame_layout.addWidget(table)
        frame.setLayout(frame_layout)
        self.frames[name] = frame
        self.tables[name] = table

    def switch_timer(self):
        if self._timer_started:
            self._stopTimer()
        else:
            self._startTimer()

    def _startTimer(self):
        self.startTimer()
        self.start_timing('protocol_timer')
        self._timer_started = True
        self.timer_switcher.setText('Stop')

    def startTimer(self):
        self.set_state('is_running', True)

    def _stopTimer(self):
        self.stopTimer()
        self.stop_timing('protocol_timer')
        self._timer_started = False  # self._time = self._time.elapsed()
        self.timer_switcher.setText('Start')

    def stopTimer(self):
        self.set_state('is_running', False)

    def on_protocol(self, t):
        cur_time = t
        if self.tables['Protocol'].model():
            data = self.tables['Protocol'].model()._data
            time_col = data['time']
            if cur_time <= (time_col.max() + self.timerInterval()):
                row_idx = None
                for i, v in enumerate(time_col):
                    if v >= cur_time:
                        row_idx = i - 1
                        break
                if row_idx is None:
                    self._stopTimer()
                else:
                    if self.watch_state('visual_row', row_idx):
                        self.tables['Protocol'].selectRow(row_idx)
                        for k in data.keys():
                            if ":" in k:
                                m,s = k.split(':')
                                if m in self.get_linked_minion_names():
                                    if s in self.get_shared_state_names(m):
                                        self.set_state_to(m,s,float(data[k][row_idx]))


    def _init_menu(self):
        self._menubar = self.menuBar()
        self._menu_file = self._menubar.addMenu('File')
        Exit = qw.QAction("Quit", self)
        Exit.setShortcut("Ctrl+Q")
        Exit.setStatusTip("Exit program")
        Exit.triggered.connect(self.close)
        self._menu_file.addAction(Exit)

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
        self._params = {"frame_rate": self.frame_rate, 'video_format': self._video_format, 'Gain': 0, 'Exposure': self.refresh_interval, 'Trigger': 0},
        for k, v in self._params.items():
            self.create_state(k, v)

    def initialize(self):
        self._init_tisgrabber()
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

    def _init_tisgrabber(self):
        self.ic = ctypes.cdll.LoadLibrary(self.TIS_DLL_DIR)
        tis.declareFunctions(self.ic)
        self.ic.IC_InitLibrary(0)
        return self.ic

    def _snapImage(self):
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
        try:
            for n, v in self.servo_dict.items():
                state = self.get_state(n)
                # if self.watch_state(n, state) and state is not None:
                #     if n == 'Trigger':
                #         if state == 1:
                #             self._snapImage()
                #             self.ic.IC_Trigger(self.hGrabber)
                # v.write(state*180)
        except:
            print(traceback.format_exc())

    def shutdown(self):
        self._port.close()

    def watch_state(self, name, val):
        if name not in self._watching_state.keys():
            self._watching_state[name] = val
            return True
        else:
            changed = val != self._watching_state[name]
            self._watching_state[name] = val
            return changed

    def __del__(self):
        self.ic.IC_StopLive(self.hGrabber)
        self.ic.IC_ReleaseGrabber(self.hGrabber)
