import os

import numpy as np

from bin.widgets.prototypes import AbstractGUIAPP, AbstractAPP
import time
import traceback

import PyQt5.QtWidgets as qw
import PyQt5.QtGui as qg
import pyqtgraph as pg

from bin.compiler.graphics import QtCompiler
from bin.gui import DataframeTable
from bin.compiler.serial_devices import OMSCompiler, ArduinoCompiler
from src.tisgrabber import tisgrabber as tis

from bin.compiler.prototypes import AbstractCompiler
from serial import Serial
# import pyfirmata2 as fmt


class MainGUICompiler(QtCompiler):
    _SERVO_MIN = 2400
    _SERVO_MAX = 9000

    def __init__(self, *args, surveillance_state={}, **kwargs):
        super(MainGUICompiler, self).__init__(*args, **kwargs)
        self._ca_frame_num = -1
        self.ca_session_num = 0
        self._camera_minions = [i for i in self.get_linked_minion_names() if 'tiscam' in i.lower()]
        self._connected_camera_minions = {}
        self._camera_param = {}
        self._videoStreams = {}
        self.camconfig_videoFormat_list_idx = None

        self._root_folder = None
        self._save_camera_list = []

        self.surveillance_state = surveillance_state

        self._tiscamHandle = tis.TIS_CAM()

        self._deviceList = self._tiscamHandle.GetDevices()

        self._servo_minion = [i for i in self.get_linked_minion_names() if 'servo' in i.lower()]
        self._aux_minion = 'AUX'

        # OMS module
        self._OMS_minion = [i for i in self.get_linked_minion_names() if 'oms' in i.lower()]
        if self._OMS_minion:
            self._OMS_minion = self._OMS_minion[0]

        self._plots = {}
        self._plots_arr = {}
        self._time_arr = np.zeros(2000, dtype=np.float64)
        self._update_surveillance_state_list()

        self._init_main_window()
        self._init_menu()

    def _update_surveillance_state_list(self):
        for k, v_list in self.surveillance_state.items():
            for v in v_list:
                val = self.get_state_from(k, v)
                val_type = type(val)
                if self._plots_arr.get(k) is None:
                    self._plots_arr[k] = {}
                if val_type in [int, float, bool]:
                    self._plots_arr[k][v] = np.zeros(2000, dtype=np.float64)
                elif val_type == np.ndarray:
                    self._plots_arr[k][v] = val
                else:
                    self._plots_arr[k][v] = None
                    self.warning(
                        f'The type of the state {k}.{v} ({val_type}) is not supported for plotting')

    def _init_main_window(self):
        self.layout_main = qw.QGridLayout()
        self.layout_CamView = qw.QHBoxLayout()

        self.layout_SavePanel = qw.QVBoxLayout()

        self.layout_SaveConfig = qw.QHBoxLayout()
        self._root_folder_textbox = qw.QLineEdit()
        self._root_folder_textbox.setReadOnly(True)
        self._root_folder_browse_btn = qw.QPushButton('Browse')
        self._root_folder_browse_btn.clicked.connect(self._browse_root_folder)
        self.layout_SaveConfig.addWidget(qw.QLabel('Save Folder:'))
        self.layout_SaveConfig.addWidget(self._root_folder_textbox)
        self.layout_SaveConfig.addWidget(self._root_folder_browse_btn)

        self.layout_SaveTrigger = qw.QHBoxLayout()
        self._filename_textbox = qw.QLineEdit()
        self._filename_textbox.setReadOnly(True)
        self._save_btn = qw.QPushButton('Start Recording')
        self._save_btn.clicked.connect(self._save_video)
        self.layout_SaveTrigger.addWidget(qw.QLabel('Filename:'))
        self.layout_SaveTrigger.addWidget(self._filename_textbox)
        self.layout_SaveTrigger.addWidget(self._save_btn)

        self.layout_SavePanel.addLayout(self.layout_SaveConfig)
        self.layout_SavePanel.addLayout(self.layout_SaveTrigger)

        # Stimulation GUI
        self.add_timer('protocol_timer', self.on_protocol)
        self.create_state('is_running', False)

        self._timer_started = False
        self.timer_switcher = qw.QPushButton('Start')
        self.timer_switcher.clicked.connect(self.switch_timer)

        self.frames = {}
        self.tables = {}
        self.addTableBox('Protocol')
        self.groupbox_layout = qw.QHBoxLayout()
        for val in self.frames.values():
            self.groupbox_layout.addWidget(val)

        self.layout_stimGUI = qw.QVBoxLayout()
        self.layout_stimGUI.addLayout(self.groupbox_layout)
        self.layout_stimGUI.addWidget(self.timer_switcher)


        #### STATE MONITOR MODULE ####
        self.layout_state_monitor = qw.QVBoxLayout()
        self.layout_state_monitor.heightForWidth(50)
        self.qtPlotWidget = pg.PlotWidget()
        self.qtPlotWidget.setBackground('w')
        self.layout_state_monitor.addWidget(self.qtPlotWidget, 5)
        for k, v_list in self.surveillance_state.items():
            for v in v_list:
                if self._plots_arr[k][v] is not None:
                    if self._plots.get(k) is None:
                        self._plots[k] = {}
                    if self._plots_arr[k][v].ndim == 2:
                        data = self._plots_arr[k][v]
                        self._plots[k][v] = []
                        for i in range(1,data.shape[1]):
                            self._plots[k][v].append(self.qtPlotWidget.plot(data[:,0], data[:,i],
                                                                   pen=pg.mkPen(np.random.randint(0, 255, 3), width=2)))
                    else:
                        self._plots[k][v] = self.qtPlotWidget.plot(self._time_arr, self._plots_arr[k][v],
                                                               pen=pg.mkPen(np.random.randint(0, 255, 3), width=2))
        self.label_ca_frame = qw.QLabel('Frame: NaN [0]')
        self.label_arduino_time = qw.QLabel('Arduino Time: NaN')
        self.btn_frame_reset = qw.QPushButton('Reset')
        self.btn_frame_reset.clicked.connect(self._reset_frame)
        self.btn_freeze_frame = qw.QPushButton('Freeze Frame!')
        self.btn_freeze_frame.setStyleSheet("background-color: light gray")
        self.btn_freeze_frame.clicked.connect(self._freeze_frame)
        self.layout_state_monitor_controller = qw.QHBoxLayout()
        self.layout_state_monitor_controller.addWidget(self.label_ca_frame, 1)
        self.layout_state_monitor_controller.addWidget(self.label_arduino_time, 1)
        self.layout_state_monitor_controller.addWidget(self.btn_freeze_frame, 1)
        self.layout_state_monitor_controller.addWidget(self.btn_frame_reset, 1)
        self.layout_state_monitor.addLayout(self.layout_state_monitor_controller, 1)

        self.layout_main.addLayout(self.layout_CamView, 0, 0, 2, 2)
        self.layout_main.addLayout(self.layout_SavePanel, 0, 2, 1, 1)
        self.layout_main.addLayout(self.layout_stimGUI, 1, 2, 1, 1)
        self.layout_main.addLayout(self.layout_state_monitor, 2, 0, 1, 3)

        self.layout_main.setColumnStretch(0, 2)
        self.layout_main.setColumnStretch(2, 1)
        self.layout_main.setRowStretch(1, 2)
        self.layout_main.setRowStretch(2, 1)

        self.main_widget = qw.QWidget()
        self.main_widget.setLayout(self.layout_main)
        self.setCentralWidget(self.main_widget)

    def _reset_frame(self):
        self.set_state_to('Aux', 'frames', 0)

    def _freeze_frame(self):
        if self.btn_freeze_frame.text() == 'Freeze Frame!':
            self.btn_freeze_frame.setStyleSheet('background-color: #dcf3ff')
            self.btn_freeze_frame.setText('Unfreeze Frame!')
            self.set_state_to('Aux', 'freeze', 1)
        else:
            self.btn_freeze_frame.setStyleSheet('background-color: light gray')
            self.btn_freeze_frame.setText('Freeze')
            self.set_state_to('Aux', 'freeze', 0)

    def _browse_root_folder(self):
        self._root_folder = str(qw.QFileDialog.getExistingDirectory(self, 'Open Folder', '.',
                                                                    qw.QFileDialog.DontUseNativeDialog))
        # For some reason the native dialog doesn't work
        self._root_folder_textbox.setText(self._root_folder)

    def _save_video(self):
        if self._save_btn.text() == 'Start Recording':
            self._save_btn.setText('Stop Recording')
            self._save_btn.setStyleSheet('background-color: yellow')
            self._save_init_time = time.perf_counter()
            self._save_filename = time.strftime('%Y%m%d_%H%M%S')
            if self._root_folder is None:
                self._root_folder = os.getcwd()
            self._save_dir = self._root_folder + '/' + self._save_filename
            os.mkdir(self._save_dir)
            self._filename_textbox.setText(self._save_filename)

            self._save_camera_list = []
            for k, v in self._videoStreams.items():
                if v[-1].isChecked():
                    self._save_camera_list.append(k)

            for cam in self._save_camera_list:
                mi_name = self._connected_camera_minions[cam]
                self.set_state_to(mi_name, 'SaveDir', self._save_dir)
                self.set_state_to(mi_name, 'SaveName', self._save_filename)
                self.set_state_to(mi_name, 'InitTime', self._save_init_time)
                self.set_state_to(mi_name, 'StreamToDisk', True)

            for servoM in self._servo_minion:
                self.set_state_to(servoM, 'SaveDir', self._save_dir)
                self.set_state_to(servoM, 'SaveName', self._save_filename)
                self.set_state_to(servoM, 'InitTime', self._save_init_time)
                self.set_state_to(servoM, 'StreamToDisk', True)

        else:
            self._save_btn.setText('Start Recording')
            self._save_btn.setStyleSheet('background-color: white')
            for cam in self._save_camera_list:
                mi_name = self._connected_camera_minions[cam]
                self.set_state_to(mi_name, 'StreamToDisk', False)
            for servoM in self._servo_minion:
                self.set_state_to(servoM, 'StreamToDisk', False)

    def _init_menu(self):
        self._menubar = self.menuBar()
        self._menu_file = self._menubar.addMenu('File')

        AddCamera = qw.QAction("Add Camera", self)
        AddCamera.setShortcut("Ctrl+O")
        AddCamera.setStatusTip("Add IC Camera")
        AddCamera.triggered.connect(self.add_camera)

        Disconnect = qw.QAction("Disconnect Camera", self)
        Disconnect.setShortcut("Ctrl+Shift+O")
        Disconnect.setStatusTip("Remove IC Camera")
        Disconnect.triggered.connect(self.remove_camera)

        Exit = qw.QAction("Quit", self)
        Exit.setShortcut("Ctrl+Q")
        Exit.setStatusTip("Exit program")
        Exit.triggered.connect(self.close)

        self._menu_file.addAction(AddCamera)
        self._menu_file.addAction(Disconnect)
        self._menu_file.addAction(Exit)

    def add_camera(self):

        self.camConfigWindow = qw.QWidget()
        self.camConfigWindow.setWindowTitle('Add Camera')
        layout_configMain = qw.QVBoxLayout()

        layout_devSelection = qw.QHBoxLayout()
        self.camconfig_camera_list = qw.QComboBox()
        self.camconfig_camera_list.addItems([i.decode('utf-8') for i in self._deviceList])
        self.camconfig_camera_list.activated.connect(self.getVideoFormat)
        self.camconfig_camera_list.currentIndexChanged.connect(self.getVideoFormat)
        layout_devSelection.addWidget(qw.QLabel('Select device:'))
        layout_devSelection.addWidget(self.camconfig_camera_list)

        layout_videoFormat = qw.QHBoxLayout()
        self.camconfig_videoFormat_list = qw.QComboBox()
        self.getVideoFormat()
        if self.camconfig_videoFormat_list_idx is not None:
            self.camconfig_videoFormat_list.setCurrentIndex(self.camconfig_videoFormat_list_idx)
        layout_videoFormat.addWidget(qw.QLabel('Select video format:'))
        layout_videoFormat.addWidget(self.camconfig_videoFormat_list)

        layout_confirm = qw.QHBoxLayout()
        self.camconfig_confirm = qw.QPushButton('Add')
        self.camconfig_confirm.setShortcut('Return')
        self.camconfig_confirm.clicked.connect(self.connect_camera)
        self.camconfig_cancel = qw.QPushButton('Cancel')
        self.camconfig_cancel.setShortcut('Esc')
        self.camconfig_cancel.clicked.connect(self.camConfigWindow.close)
        layout_confirm.addWidget(self.camconfig_confirm)
        layout_confirm.addWidget(self.camconfig_cancel)

        layout_configMain.addLayout(layout_devSelection)
        layout_configMain.addLayout(layout_videoFormat)
        layout_configMain.addLayout(layout_confirm)

        self.camConfigWindow.setLayout(layout_configMain)
        self.camConfigWindow.show()

    def remove_camera(self):
        self.disconnectWindow = qw.QWidget()
        self.disconnectWindow.setWindowTitle('Choose camera to disconnect')
        layout_configMain = qw.QVBoxLayout()

        layout_devSelection = qw.QHBoxLayout()
        self.camdisconn_camera_list = qw.QComboBox()
        self.camdisconn_camera_list.addItems([i.decode('utf-8') for i in self._deviceList])
        layout_devSelection.addWidget(qw.QLabel('Select device to remove:'))
        layout_devSelection.addWidget(self.camdisconn_camera_list)

        layout_confirm = qw.QHBoxLayout()
        self.camdisconn_confirm = qw.QPushButton('Disconnect')
        self.camdisconn_confirm.setShortcut('Return')
        self.camdisconn_confirm.clicked.connect(self.disconnect_camera)
        self.camdisconn_cancel = qw.QPushButton('Cancel')
        self.camdisconn_cancel.setShortcut('Esc')
        self.camdisconn_cancel.clicked.connect(self.disconnectWindow.close)
        layout_confirm.addWidget(self.camdisconn_confirm)
        layout_confirm.addWidget(self.camdisconn_cancel)

        layout_configMain.addLayout(layout_devSelection)
        layout_configMain.addLayout(layout_confirm)

        self.disconnectWindow.setLayout(layout_configMain)
        self.disconnectWindow.show()

    def getVideoFormat(self):
        self._tiscamHandle.open(self.camconfig_camera_list.currentText())
        video_formats = [i.decode('utf-8') for i in self._tiscamHandle.GetVideoFormats()]
        self.camconfig_videoFormat_list.clear()
        self.camconfig_videoFormat_list.addItems(video_formats)

    def connect_camera(self):
        cameraName = self.camconfig_camera_list.currentText()
        videoFormat = self.camconfig_videoFormat_list.currentText()
        hasGUI = cameraName in self._connected_camera_minions.keys()
        self._connect_camera(cameraName, videoFormat)
        if not hasGUI:
            self.setupCameraFrameGUI(cameraName)
        self.camconfig_videoFormat_list_idx = self.camconfig_camera_list.currentIndex()
        self.camConfigWindow.close()

    def _connect_camera(self, cameraName, videoFormat=None):
        if videoFormat is not None:
            self._camera_param[cameraName] = {
                'VideoFormat': videoFormat,
                'StreamToDisk': None,
                'SaveDir': None,
                'SaveName': None,
                'InitTime': None,
            }

        if cameraName in self._connected_camera_minions.keys():
            self.error('Camera already connected')
        else:
            free_minion = [i for i in self._camera_minions if i not in self._connected_camera_minions.values()]
            if not free_minion:
                self.error('No more camera minion available')
            else:
                mi = free_minion[0]
                self.set_state_to(mi, 'CameraName', cameraName)
                for k, v in self._camera_param[cameraName].items():
                    if v is not None:
                        self.set_state_to(mi, k, v)
                self._camera_param[cameraName][
                    'buffer_name'] = f"frame_{self._camera_param[cameraName]['VideoFormat']}".replace(' ', '_')
                self._connected_camera_minions[cameraName] = mi

    def disconnect_camera(self):
        cameraName = self.camconfig_camera_list.currentText()
        self._disconnect_camera(cameraName)
        self.disconnectWindow.close()

    def _disconnect_camera(self, cameraName, saveConfig=False, saveGUI=False):

        if cameraName not in self._connected_camera_minions.keys():
            self.error('Camera has not been connected')
        else:
            self.set_state_to(self._connected_camera_minions[cameraName], 'CameraName', None)
            self._connected_camera_minions.pop(cameraName)
            if not saveConfig:
                self._camera_param.pop(cameraName)
            if not saveGUI:
                for i in self._videoStreams[cameraName]:
                    self.layout_CamView.removeWidget(i)
                    i.deleteLater()
                self._videoStreams.pop(cameraName)

    def refresh(self, cameraName):
        self._disconnect_camera(cameraName, saveConfig=True, saveGUI=True)
        time.sleep(.5)
        self._connect_camera(cameraName)

    def setupCameraFrameGUI(self, cameraName):
        self._videoStreams[cameraName] = [pg.ImageView(name=cameraName, ),
                                          qw.QPushButton('Refresh'),
                                          qw.QPushButton('toggleImageSettings'),
                                          qw.QCheckBox('Save')]
        cameraWidget = self._videoStreams[cameraName][0]
        refresh_btn = self._videoStreams[cameraName][1]
        toggle_btn = self._videoStreams[cameraName][2]
        save_checkbox = self._videoStreams[cameraName][3]

        layout = qw.QGridLayout()
        cameraWidget: pg.ImageView
        cameraWidget.setColorMap(pg.colormap.get('CET-L1'))
        cameraWidget.show()
        refresh_btn.clicked.connect(lambda: self.refresh(cameraName))
        toggle_btn.clicked.connect(lambda: self.toggle_ImageViewControl(cameraName))
        self.toggle_ImageViewControl(cameraName)
        layout.addWidget(cameraWidget, 0, 0, 2, 3)
        layout.addWidget(refresh_btn, 2, 0, 1, 1)
        layout.addWidget(toggle_btn, 2, 1, 1, 1)
        layout.addWidget(save_checkbox, 2, 2, 1, 1)

        self.layout_CamView.addLayout(layout)

    def toggle_ImageViewControl(self, cameraName):
        cameraWidget = self._videoStreams[cameraName][0]
        if cameraWidget.ui.menuBtn.isVisible():
            cameraWidget.ui.roiBtn.hide()
            cameraWidget.ui.menuBtn.hide()
            cameraWidget.ui.histogram.hide()
        else:
            cameraWidget.ui.roiBtn.show()
            cameraWidget.ui.menuBtn.show()
            cameraWidget.ui.histogram.show()

    def on_time(self, t):
        for camName, mi in self._connected_camera_minions.items():
            try:
                frame = self.get_state_from(mi, self._camera_param[camName]['buffer_name'])
                if frame is not None:
                    camWidget = self._videoStreams[camName][0]
                    camWidget: pg.ImageView
                    if camWidget.image is None:
                        _init_auto_level = True
                    camWidget.setImage(frame[:, :, 0], autoRange=False, autoLevels=False)
                    if _init_auto_level:
                        camWidget.autoLevels()
            except:
                self.debug('Error when trying to get frame from camera minion.')
                self.debug(traceback.format_exc())

        self.update_plot_arr(t)
        self.update_aux_state()
        self._processHandler.on_time(t)

    def update_aux_state(self):
        arduino_time = self.get_state_from(self._aux_minion, 'arduino_time')
        ca_frame_num = self.get_state_from(self._aux_minion, 'ca_frame_num')

        if type(ca_frame_num) == int and type(arduino_time) == int:
            arduino_time /= 1000  # convert to seconds

            if self._ca_frame_num - ca_frame_num > 0:  # When the ca_frame_num is reset, add 1 to the ca_session_num
                self.ca_session_num += 1

            if self.ca_session_num > 0:  # for the second session and afterwards, preserve the last ca_frame_num in the previous session
                if ca_frame_num > 0:
                    self.label_ca_frame.setText(f"Ca session num: {ca_frame_num} [{self.ca_session_num}] ")  # To preserve the last ca_frame_num
            else:
                self.label_ca_frame.setText(f"Ca session num: {ca_frame_num} [0]")

            self.label_arduino_time.setText(f"Arduino time: {(arduino_time):.2f} s")
            self._ca_frame_num = ca_frame_num

    def update_plot_arr(self, t):
            self._time_arr[:-1] = self._time_arr[1:]
            self._time_arr[-1] = t
            for k, v_list in self.surveillance_state.items():
                for v in v_list:
                    if self._plots_arr[k][v] is not None:
                        self._plots_arr[k][v][:-1] = self._plots_arr[k][v][1:]
                        new_val = self.get_state_from(k, v)
                        if new_val is not None:
                            if type(new_val) is np.ndarray:
                                for i in range(len(self._plots[k][v])):
                                    self._plots[k][v][i].setData(new_val[:, 0], new_val[:, i+1])
                            else:
                                self._plots_arr[k][v][-1] = new_val
                                self._plots[k][v].setData(self._time_arr, self._plots_arr[k][v])

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
                                m, s = k.split(':')
                                if m in self.get_linked_minion_names():
                                    if s in self.get_shared_state_names(m):
                                        if 'servo' in m.lower():
                                            state = float(data[k][row_idx] * (
                                                    self._SERVO_MAX - self._SERVO_MIN) + self._SERVO_MIN)
                                        else:
                                            state = float(data[k][row_idx])
                                        self.set_state_to(m, s, state)


class MainGUI(AbstractGUIAPP):
    def __init__(self, *args, surveillance_state=None, **kwargs):
        super(MainGUI, self).__init__(*args, **kwargs)
        self._surveillance_state = surveillance_state

    def initialize(self):
        super().initialize()
        self._win = MainGUICompiler(self, surveillance_state=self._surveillance_state)
        self.info("Main GUI initialized.")
        self._win.show()


class OMSInterface(AbstractAPP):
    def __init__(self, *args, VID=None, PID=None, mw_size=1, **kwargs):
        super(OMSInterface, self).__init__(*args, **kwargs)
        self._VID = VID
        self._PID = PID
        self._mw_size = mw_size

    def initialize(self):
        super().initialize()
        self._compiler = OMSCompiler(self, VID=self._VID, PID=self._PID, mw_size=self._mw_size)
        self.info("OMS compiler initialized.")


class PeakDetectorCompiler(AbstractCompiler):

    def __init__(self, *args, port_name='COM7', **kwargs):
        super(PeakDetectorCompiler, self).__init__(*args, **kwargs)
        self._session_start_time = 0
        self._port_name = port_name
        self._port = None
        self.input_pin_dict = {}
        self.output_pin_dict = {}

        self._port = Serial(self._port_name, baudrate=115200, timeout=1)

        self._buffer_data = np.zeros([5000,3], dtype=np.int64)
        self._last_frame_num = 0

        self.create_shared_buffer('mirPos', self._buffer_data)
        self.create_state('arduino_time', 0)
        self.create_state('ca_frame_num', 0)
        self.create_state('freeze', 0)

    def detect_frame(self):
        baseline_thre = 100
        reset_grad_thre = -150
        try:
            getData = self._port.readline()
            data = getData.decode('utf-8')
            if "---" in data and "+++" in data:
                data = data.split('---')[1].split('+++')[0]
                data = data.split(',')

                arduino_time = int(data[0])
                cur_frame_num = int(data[2])

                self.set_state('arduino_time', arduino_time)  # broadcast arduino time

                frame_changed = cur_frame_num - self._last_frame_num  # omit report if frame number is not changed
                self._last_frame_num = cur_frame_num

                if frame_changed != 0:  # if frame number is changed, report frame number
                    self.set_state('ca_frame_num', cur_frame_num)

                ##### For debugging purpose ####
                # self._buffer_data[:-1, :] = self._buffer_data[1:, :]
                # self._buffer_data[-1, :] = [int(data[0]), int(data[1]), 500*(frame_changed>0)]
                # self.set_state('mirPos', self._buffer_data)

        except:
            pass
        # except Exception as e:
            # self.error(e)


    def on_time(self, t):
        if not self.get_state('freeze'):
            self.detect_frame()

    def on_close(self):
        self._outputfile_handle.close()
        super().on_close()

class ArduinoInterface(AbstractAPP):
    def __init__(self, *args, port_name=None, **kwargs):
        super(ArduinoInterface, self).__init__(*args, **kwargs)
        self._param_to_compiler = {'port_name': port_name}

    def initialize(self):
        super().initialize()
        self._compiler = PeakDetectorCompiler(self, **self._param_to_compiler)
        self.info("Arduino compiler initialized.")
