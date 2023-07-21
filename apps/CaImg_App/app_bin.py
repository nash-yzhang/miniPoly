import os
import getpass
import shutil

import numpy as np
import pandas as pd

import time
import traceback

import PyQt5.QtWidgets as qw
import PyQt5.QtCore as qc
import paramiko
import pyqtgraph as pg

from bin.compiler.graphics import QtCompiler
from bin.gui import DataframeTable, DataframeModel, CustomizableCloseEventWidget
from src.tisgrabber import tisgrabber as tis

from bin.compiler.prototypes import StreamingCompiler, AbstractCompiler
from serial import Serial


class DirSelectorLineEdit(qw.QLineEdit):
    dbClicked = qc.pyqtSignal()

    def __init__(self, placeHolderText=''):
        super().__init__()
        self.setPlaceholderText(placeHolderText)

    def event(self, event):
        if event.type() == qc.QEvent.Type.MouseButtonDblClick:
            self.dbClicked.emit()
        return super().event(event)

class MainGUI(QtCompiler):

    def __init__(self, *args, surveillance_state={}, **kwargs):
        super(MainGUI, self).__init__(*args, **kwargs)

        self._wrapper_minion = 'DATAWRAPPER'
        self._IO_minion = 'IO'
        self._scanlistener_minion = 'SCAN'
        self._linked_minion_names = self.get_linked_minion_names()
        self._servo_minion = [i for i in self._linked_minion_names if 'servo' in i.lower()]
        self._OMS_minion = [i for i in self._linked_minion_names if 'oms' in i.lower()]
        self._camera_minions = [i for i in self._linked_minion_names if 'cam' in i.lower()]

        self._ca_frame_num = -1
        self.ca_session_num = 0
        self._connected_camera_minions = {}
        self._camera_param = {}
        self._videoStreams = {}
        self.camconfig_videoFormat_list_idx = None

        self._root_folder = None
        self._save_camera_list = []

        self._debug_sweep_started = False
        self._debug_sweep_btn = None
        self._sweep_step = 15
        self._sweep_timer = qc.QTimer()
        self._sweep_timer.timeout.connect(self._exec_sweep)

        self.surveillance_state = surveillance_state

        self._tiscamHandle = tis.TIS_CAM()
        self._deviceList = self._tiscamHandle.GetDevices()

        # OMS module
        if self._OMS_minion:
            self._OMS_minion = self._OMS_minion[0]

        self._plots = {}
        self._plots_arr = {}
        self._time_arr = np.zeros(2000, dtype=np.float64)
        self._update_surveillance_state_list()

        self._sessionNum = 0
        self._lastSessionNum = 0
        self._animalID = ''

        # Create stimulus related states
        self.create_state('runSignal', False, use_buffer=True)
        self.create_state('protocolFn', '', use_buffer=False)
        self.create_state('cmd_idx', 0, use_buffer=True)

        # create streaming related states
        self.create_state('SaveDir', '')
        self.create_state('SaveName', '')
        self.create_state('StreamToDisk', False, use_buffer=True)


        self._init_main_window()
        self._init_menu()

        self.remotePC_login()


    def remotePC_login(self):
        self._login_win = qw.QWidget()
        login_layout = qw.QVBoxLayout()
        user_textbox = qw.QLineEdit()
        user_textbox.setPlaceholderText('Username')
        pw_textbox = qw.QLineEdit()
        pw_textbox.setPlaceholderText('Password')
        pw_textbox.setEchoMode(qw.QLineEdit.Password)
        login_btn = qw.QPushButton('send')
        login_btn.setShortcut('Return')
        login_btn.clicked.connect(self.send_login_message)
        login_layout.addWidget(user_textbox)
        login_layout.addWidget(pw_textbox)
        login_layout.addWidget(login_btn)
        self._login_win.setLayout(login_layout)
        self._login_win.setWindowModality(qc.Qt.ApplicationModal)
        self._login_win.show()

    def send_login_message(self):
        user = self._login_win.layout().itemAt(0).widget().text()
        pw = self._login_win.layout().itemAt(1).widget().text()
        self._login_win.close()
        self.send(self._wrapper_minion, 'connect', (user, pw))

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
        # self.layout_main = qw.QGridLayout()
        self.layout_main = qw.QVBoxLayout()
        self.layout_CamView = qw.QHBoxLayout()

        self.layout_SavePanel = qw.QVBoxLayout()

        self.layout_SaveConfig = qw.QHBoxLayout()
        self._root_folder_textbox = DirSelectorLineEdit()
        self._root_folder_textbox.dbClicked.connect(self._browse_root_folder)
        self._root_folder_textbox.textChanged.connect(self._update_root_folder)
        self.layout_SaveConfig.addWidget(qw.QLabel('Save Folder:'))
        self._filename_textbox = qw.QLineEdit()
        self._filename_textbox.setReadOnly(True)
        self.layout_SaveConfig.addWidget(self._root_folder_textbox)
        self.layout_SaveConfig.addWidget(qw.QLabel('Filename:'))
        self.layout_SaveConfig.addWidget(self._filename_textbox)

        self.layout_SaveTrigger = qw.QHBoxLayout()
        self._sessionNum_textbox = qw.QLineEdit()
        self._sessionNum_textbox.textChanged.connect(self._update_session_num)
        self._sessionNum_textbox.setPlaceholderText('Session Number')
        self._animalID_textbox = qw.QLineEdit()
        self._animalID_textbox.textChanged.connect(self._update_animal_num)
        self._animalID_textbox.setPlaceholderText('Animal ID')
        self._save_btn = qw.QPushButton('Start Recording')
        self._save_btn.clicked.connect(self._save_video)
        self.layout_SaveTrigger.addWidget(self._sessionNum_textbox)
        self.layout_SaveTrigger.addWidget(self._animalID_textbox)
        self.layout_SaveTrigger.addWidget(self._save_btn)

        self.layout_SavePanel.addLayout(self.layout_SaveConfig)
        self.layout_SavePanel.addLayout(self.layout_SaveTrigger)

        # Stimulation GUI
        self.add_timer('protocol_timer', self.on_protocol)

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
        # self.qtPlotWidget.setBackground('w')
        self.layout_state_monitor.addWidget(self.qtPlotWidget, 5)
        for k, v_list in self.surveillance_state.items():
            for v in v_list:
                if self._plots_arr[k][v] is not None:
                    if self._plots.get(k) is None:
                        self._plots[k] = {}
                    if self._plots_arr[k][v].ndim == 2:
                        data = self._plots_arr[k][v]
                        self._plots[k][v] = []
                        for i in range(1, data.shape[1]):
                            self._plots[k][v].append(self.qtPlotWidget.plot(data[:, 0], data[:, i],
                                                                            pen=pg.mkPen(np.random.randint(0, 255, 3),
                                                                                         width=2)))
                    else:
                        self._plots[k][v] = self.qtPlotWidget.plot(self._time_arr, self._plots_arr[k][v],
                                                                   pen=pg.mkPen(np.random.randint(0, 255, 3), width=2))
        self.label_ca_frame = qw.QLabel('Frame: NaN [0]')
        self.label_timestamp = qw.QLabel('Arduino Time: NaN')
        # self.btn_freeze_frame = qw.QPushButton('Freeze Frame!')
        # self.btn_freeze_frame.setStyleSheet("background-color: light gray")
        # self.btn_freeze_frame.clicked.connect(self._freeze_frame)
        self.layout_state_monitor_controller = qw.QHBoxLayout()
        self.layout_state_monitor_controller.addWidget(self.label_ca_frame, 1)
        self.layout_state_monitor_controller.addWidget(self.label_timestamp, 1)
        # self.layout_state_monitor_controller.addWidget(self.btn_freeze_frame, 1)
        self.layout_state_monitor.addLayout(self.layout_state_monitor_controller, 1)

        top_hori_splitter = qw.QSplitter()
        self.widget_CamView = qw.QWidget()
        self.widget_CamView.setLayout(self.layout_CamView)
        self.widget_right_top_panel = qw.QWidget()
        self.layout_right_top_panel = qw.QVBoxLayout()
        self.widget_SavePanel = qw.QWidget()
        self.widget_SavePanel.setLayout(self.layout_SavePanel)
        self.widget_stimGUI = qw.QWidget()
        self.widget_stimGUI.setLayout(self.layout_stimGUI)
        self.layout_right_top_panel.addWidget(self.widget_SavePanel)
        self.layout_right_top_panel.addWidget(self.widget_stimGUI)
        self.widget_right_top_panel.setLayout(self.layout_right_top_panel)
        top_hori_splitter.addWidget(self.widget_CamView)
        top_hori_splitter.addWidget(self.widget_right_top_panel)
        self.widget_state_monitor = qw.QWidget()
        self.widget_state_monitor.setLayout(self.layout_state_monitor)
        main_vert_splitter = qw.QSplitter(qc.Qt.Vertical)
        main_vert_splitter.addWidget(top_hori_splitter)
        main_vert_splitter.addWidget(self.widget_state_monitor)
        self.layout_main.addWidget(main_vert_splitter)

        self.main_widget = qw.QWidget()
        self.main_widget.setLayout(self.layout_main)
        self.setCentralWidget(self.main_widget)

    def _update_animal_num(self):
        self._animalID = self._animalID_textbox.text()

    def _update_session_num(self):
        self._sessionNum = self._sessionNum_textbox.text()

    def _update_root_folder(self):
        self._root_folder = self._root_folder_textbox.text()

    def _browse_root_folder(self):
        self._root_folder = str(qw.QFileDialog.getExistingDirectory(self, 'Open Folder', '.',
                                                                    qw.QFileDialog.DontUseNativeDialog))
        # For some reason the native dialog doesn't work
        self._root_folder_textbox.setText(self._root_folder)

    def _start_recording_check(self):
        err = 0
        if self._animalID == '':
            err = 1
        if self._sessionNum <= self._lastSessionNum:
            err += 2

        return err

    def _save_video(self):
        if self._save_btn.text() == 'Start Recording':
            err_code = self._start_recording_check()
            if err_code == 0:
                self._save_btn.setText('Stop Recording')
                self._save_btn.setStyleSheet('background-color: yellow')
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

                self.set_state('SaveDir', self._save_dir)
                self.set_state('SaveName', self._save_filename)
                self.set_state('StreamToDisk', True)
            elif err_code == 1:
                # If no new session number, popup a warning and focus on the session number textbox
                qw.QMessageBox.warning(self, 'Warning', 'Please enter the animal ID')
                self._animalID_textbox.setFocus()
            elif err_code == 2:
                qw.QMessageBox.warning(self, 'Warning', 'Please enter the new session number!')
                self._sessionNum_textbox.setFocus()
            elif err_code == 3:
                qw.QMessageBox.warning(self, 'Warning', 'Please enter the animal ID and the new session number!')
                self._animalID_textbox.setFocus()

        else:
            self._save_btn.setText('Start Recording')
            self._save_btn.setStyleSheet('background-color: white')
            self.set_state('StreamToDisk', False)
            self.send(self._wrapper_minion, 'data', (self._save_dir, self._animalID, self._sessionNum))
            self._lastSessionNum = self._sessionNum
            # for cam in self._save_camera_list:
            #     mi_name = self._connected_camera_minions[cam]
            # for servoM in self._servo_minion:
            #     self.set_state_to(servoM, 'StreamToDisk', False)

    def _init_menu(self):
        self._menubar = self.menuBar()
        self._menu_file = self._menubar.addMenu('File')

        Exit = qw.QAction("Quit", self)
        Exit.setShortcut("Ctrl+Q")
        Exit.setStatusTip("Exit program")
        Exit.triggered.connect(self.close)

        self._menu_file.addAction(Exit)

        self._menu_camera = self._menubar.addMenu('Camera')

        AddCamera = qw.QAction("Add Camera", self)
        AddCamera.setShortcut("Ctrl+O")
        AddCamera.setStatusTip("Add IC Camera")
        AddCamera.triggered.connect(self.add_camera)

        Disconnect = qw.QAction("Disconnect Camera", self)
        Disconnect.setShortcut("Ctrl+Shift+O")
        Disconnect.setStatusTip("Remove IC Camera")
        Disconnect.triggered.connect(self.remove_camera)

        self._menu_camera.addAction(AddCamera)
        self._menu_camera.addAction(Disconnect)

        self._menu_servo = self._menubar.addMenu('Servo')

        DebugServo = qw.QAction("Debug Servo", self)
        DebugServo.setStatusTip("Debug Servo")
        DebugServo.triggered.connect(self.debug_servo)

        ServoConsole = qw.QAction("Servo Console", self)
        ServoConsole.setShortcut("Ctrl+Shift+M")
        ServoConsole.setStatusTip("Servo Console")
        ServoConsole.triggered.connect(self.servo_console)

        self._menu_servo.addAction(DebugServo)
        self._menu_servo.addAction(ServoConsole)

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

    def debug_servo(self):
        '''
        Init gui with 4 text input and 2 buttons.
        the 4 text input should be stacked vertically.
        text input 1: "Mouse_servo_dist"; text input 2: "Extended_arm_length"
        text input 3: "azimuth"; text input 4 "radius";
        The 2 buttons should be at the bottom row of the gui.
        Button 1 is "Go to" and button 2 is "Sweep";
        '''

        self.debug_servo_window = CustomizableCloseEventWidget()
        self.debug_servo_window.setWindowTitle('Servo Debugger')
        self.debug_servo_window.set_close_event(self._close_debug_servo)
        self.debug_servo_window.resize(300, 200)
        layout = qw.QVBoxLayout()

        layout_mouse_servo_dist = qw.QHBoxLayout()
        self.debug_servo_window.label_mouse_servo_dist = qw.QLabel('Mouse_servo_dist')
        self.debug_servo_window.text_mouse_servo_dist = qw.QSpinBox()
        self.debug_servo_window.text_mouse_servo_dist.setRange(0, 300)
        self.debug_servo_window.text_mouse_servo_dist.valueChanged.connect(
            lambda: self._update_debug_param('mouse_servo_dist'))
        self.debug_servo_window.text_mouse_servo_dist.setValue(220)
        layout_mouse_servo_dist.addWidget(self.debug_servo_window.label_mouse_servo_dist)
        layout_mouse_servo_dist.addWidget(self.debug_servo_window.text_mouse_servo_dist)

        layout_extended_arm_length = qw.QHBoxLayout()
        self.debug_servo_window.label_extended_arm_length = qw.QLabel('extended_arm_length')
        self.debug_servo_window.text_extended_arm_length = qw.QSpinBox()
        self.debug_servo_window.text_extended_arm_length.setRange(80, 150)
        self.debug_servo_window.text_extended_arm_length.valueChanged.connect(
            lambda: self._update_debug_param('extended_arm_length'))
        self.debug_servo_window.text_extended_arm_length.setValue(95)
        layout_extended_arm_length.addWidget(self.debug_servo_window.label_extended_arm_length)
        layout_extended_arm_length.addWidget(self.debug_servo_window.text_extended_arm_length)

        layout_azimuth = qw.QHBoxLayout()
        self.debug_servo_window.label_azimuth = qw.QLabel('azimuth')
        self.debug_servo_window.text_azimuth = qw.QSpinBox()
        self.debug_servo_window.text_azimuth.setRange(-1, 180)
        self.debug_servo_window.text_azimuth.valueChanged.connect(lambda: self._update_debug_param('target_azi'))
        self.debug_servo_window.text_azimuth.setValue(-1)
        layout_azimuth.addWidget(self.debug_servo_window.label_azimuth)
        layout_azimuth.addWidget(self.debug_servo_window.text_azimuth)

        layout_radius = qw.QHBoxLayout()
        self.debug_servo_window.label_radius = qw.QLabel('radius')
        self.debug_servo_window.text_radius = qw.QSpinBox()
        self.debug_servo_window.text_radius.setRange(-1, 50)
        self.debug_servo_window.text_radius.valueChanged.connect(lambda: self._update_debug_param('target_r'))
        self.debug_servo_window.text_radius.setValue(-1)
        layout_radius.addWidget(self.debug_servo_window.label_radius)
        layout_radius.addWidget(self.debug_servo_window.text_radius)

        layout_actions = qw.QHBoxLayout()
        self.debug_servo_window.button_reset = qw.QPushButton('reset')
        self.debug_servo_window.button_reset.clicked.connect(self.debug_servo_reset)
        self.debug_servo_window.button_SWEEP = qw.QPushButton('sweep')
        self.debug_servo_window.button_SWEEP.clicked.connect(self.sweep_servo)
        layout_actions.addWidget(self.debug_servo_window.button_SWEEP)
        layout_actions.addWidget(self.debug_servo_window.button_reset)

        layout.addLayout(layout_mouse_servo_dist)
        layout.addLayout(layout_extended_arm_length)
        layout.addLayout(layout_azimuth)
        layout.addLayout(layout_radius)
        layout.addLayout(layout_actions)

        self.debug_servo_window.setLayout(layout)
        self.debug_servo_window.show()

    def debug_servo_reset(self):
        self.debug_servo_window.text_azimuth.setValue(-1)
        self.debug_servo_window.text_radius.setValue(-1)

    def sweep_servo(self):
        if self._debug_sweep_started:
            self._debug_sweep_started = False
            self.set_state_to(self._servo_minion[0], 'target_azi', -1)
            self.set_state_to(self._servo_minion[0], 'target_r', -1)
            self._sweep_timer.stop()
            self.debug_servo_window.button_SWEEP.setText('Sweep')
        else:
            self._debug_sweep_started = True
            self.set_state_to(self._servo_minion[0], 'mouse_servo_dist',
                              float(self.debug_servo_window.text_mouse_servo_dist.text()))
            self.set_state_to(self._servo_minion[0], 'extended_arm_length',
                              float(self.debug_servo_window.text_extended_arm_length.text()))
            self.set_state_to(self._servo_minion[0], 'target_azi', float(self.debug_servo_window.text_azimuth.value()))
            self.set_state_to(self._servo_minion[0], 'target_r', float(self.debug_servo_window.text_radius.value()))
            self._sweep_timer.start(500)
            self.debug_servo_window.button_SWEEP.setText('Stop')

    def _update_debug_param(self, param_name):
        if param_name == 'mouse_servo_dist':
            self.set_state_to(self._servo_minion[0], 'mouse_servo_dist',
                              float(self.debug_servo_window.text_mouse_servo_dist.value()))
        elif param_name == 'extended_arm_length':
            self.set_state_to(self._servo_minion[0], 'extended_arm_length',
                              float(self.debug_servo_window.text_extended_arm_length.value()))
        elif param_name == "target_azi":
            self.set_state_to(self._servo_minion[0], 'target_azi', float(self.debug_servo_window.text_azimuth.value()))
        elif param_name == "target_r":
            self.set_state_to(self._servo_minion[0], 'target_r', float(self.debug_servo_window.text_radius.value()))

    def _exec_sweep(self):
        tar_azi = self.debug_servo_window.text_azimuth.value() + self._sweep_step
        if tar_azi > 180:
            tar_azi = 180
            self._sweep_step *= -1
        elif tar_azi < 0:
            tar_azi = 0
            self._sweep_step *= -1
        self.debug_servo_window.text_azimuth.setValue(tar_azi)
        self.set_state_to(self._servo_minion[0], 'target_azi', tar_azi)
        self.set_state_to(self._servo_minion[0], 'target_r', float(self.debug_servo_window.text_radius.value()))

    def _close_debug_servo(self, event):
        self.debug_servo_reset()
        return True

    def servo_console(self):
        self._servo_console = qw.QWidget()
        self._servo_console.setWindowTitle('Servo Console')
        self._servo_console.setWindowModality(qc.Qt.ApplicationModal)
        self._servo_console.setAttribute(qc.Qt.WA_DeleteOnClose)

        layout = qw.QHBoxLayout()

        self._servo_console.label_azi = qw.QLabel('Command: ')
        self._servo_console.text_azi = qw.QLineEdit()
        self._servo_console.text_azi.returnPressed.connect(self._send_serial_cmd)

        layout.addWidget(self._servo_console.label_azi)
        layout.addWidget(self._servo_console.text_azi)

        self._servo_console.setLayout(layout)
        self._servo_console.show()

    def _send_serial_cmd(self):
        self.set_state_to(self._servo_minion[0], 'serial_cmd', self._servo_console.text_azi.text())
        self._servo_console.text_azi.setText('')

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
        self.update_scan_state()
        self._processHandler.on_time(t)

    def update_scan_state(self):
        timestamp = self.get_state_from(self._scanlistener_minion, 'timestamp')
        ca_frame_num = self.get_state_from(self._scanlistener_minion, 'ca_frame_num')

        timestamp /= 1000  # convert to seconds

        if self._ca_frame_num - ca_frame_num > 0:  # When the ca_frame_num is reset, add 1 to the ca_session_num
            self.ca_session_num += 1

        if self.ca_session_num > 0:  # for the second session and afterwards, preserve the last ca_frame_num in the previous session
            if ca_frame_num > 0:
                self.label_ca_frame.setText(
                    f"Ca session num: {ca_frame_num} [{self.ca_session_num}] ")  # To preserve the last ca_frame_num
        else:
            self.label_ca_frame.setText(f"Ca session num: {ca_frame_num} [0]")

        self.label_timestamp.setText(f"Arduino time: {(timestamp):.2f} s")
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
                                self._plots[k][v][i].setData(new_val[:, 0], new_val[:, i + 1])
                        else:
                            self._plots_arr[k][v][-1] = new_val
                            self._plots[k][v].setData(self._time_arr, self._plots_arr[k][v])

    def addTableBox(self, name):
        frame = qw.QGroupBox(self)
        frame.setTitle(name)
        table = DataframeTable(self.centralWidget())
        browse_btn = qw.QPushButton('Browse')
        browse_btn.clicked.connect(lambda: self.browse_table(name))
        frame_layout = qw.QVBoxLayout()
        frame_layout.addWidget(table)
        frame_layout.addWidget(browse_btn)
        frame.setLayout(frame_layout)
        self.frames[name] = frame
        self.tables[name] = table

    def browse_table(self, name):
        # open file dialog for browsing data file (start from the current directory)
        file_name = qw.QFileDialog.getOpenFileName(self, 'Open file', os.getcwd(), "Excel table (*.xlsx *.xls)",
                                                   options=qw.QFileDialog.DontUseNativeDialog)
        if file_name[0] != '':
            self.tables[name].setModel(DataframeModel(data=pd.read_excel(file_name[0])))
            self.set_state('protocolFn', '')
            time.sleep(0.5)
            self.set_state('protocolFn', file_name[0])

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
        self.set_state('runSignal', True)

    def _stopTimer(self):
        self.stopTimer()
        self.stop_timing('protocol_timer')
        self._timer_started = False  # self._time = self._time.elapsed()
        self.timer_switcher.setText('Start')

    def stopTimer(self):
        self.set_state('runSignal', False)

    def on_protocol(self, t):
        if self.tables['Protocol'].model():
            cmd_idx = self.get_state('cmd_idx')
            if self.watch_state('visual_row', cmd_idx):
                self.tables['Protocol'].selectRow(cmd_idx)
                if cmd_idx == -1:
                    self._stopTimer()


class ScanListener(StreamingCompiler):

    def __init__(self, *args, port_name='COM7', **kwargs):
        super(ScanListener, self).__init__(*args, **kwargs)
        self._session_start_time = 0
        self._port_name = port_name
        self._port = None
        self.input_pin_dict = {}
        self.output_pin_dict = {}

        try:
            self._port = Serial(self._port_name, baudrate=115200, timeout=0.001)
        except Exception as e:
            self.error(e)
            self.set_state('status', -1)

        self._last_frame_num = 0
        self._last_time = 0
        self._serial_buffer = b''

        self.create_state('timestamp', 0)
        self.create_streaming_state('timestamp',
                                    0)  # local copy of the shared state to reduce the time in accessing the shared buffer
        self.create_streaming_state('ca_frame_num', 0, shared=True, use_buffer=False)

    def on_time(self, t):
        t = time.perf_counter_ns()
        # read the last complete line started with "---" and ended with "+++" from serial port
        getData = self._serial_buffer + self._port.read(self._port.inWaiting())
        data = b''
        if b'\n' in getData:
            data = getData.split(b'\n')
            data = [i for i in data if i != b'']
            if len(data) > 1:
                self._serial_buffer = data[-1]
                data = data[-2]
        else:
            self._serial_buffer = data

        if b"---" in data and b"+++" in data:
            try:
                data = data.decode('utf8')
            except:
                self.error('serial data decode error; data: %s' % data)
                return
            data = data.split('---')[1].split('+++')[0]
            data = data.split(',')
            if len(data) == 3:
                if data[1].isdigit() and data[2].isdigit():
                    timestamp = int(data[0])
                    cur_frame_num = int(data[2])
                    #
                    self.set_state('timestamp', timestamp)  # broadcast arduino time
                    self.set_streaming_state('timestamp', timestamp)  # broadcast arduino time
                    #
                    frame_changed = cur_frame_num - self._last_frame_num  # omit report if frame number is not changed
                    if frame_changed != 0:  # if frame number is changed, report frame number
                        # print(f"Time: {timestamp}, Frame: {cur_frame_num}")
                        self.set_streaming_state('ca_frame_num', cur_frame_num)
                        self._last_frame_num = cur_frame_num
            else:
                self.error('serial data error;  data: %s' % data)

            # self._port.reset_input_buffer()

        #     ##### For debugging purpose ####
        #     self._buffer_data[:-1, :] = self._buffer_data[1:, :]
        #     self._buffer_data[-1, :] = [int(data[0]), int(data[1]), 500*(frame_changed>0)]
        #     self.set_state('mirPos', self._buffer_data)
        self._last_time = t
        super().on_time(t)

    def on_close(self):
        super().on_close()


class DataWrapper(AbstractCompiler):

    def __init__(self, *args, trigger_minion=None, remote_IP_address=None, remote_dir='D:\\data\\', netdrive_dir="\\\\nas3\\datastore_bonhoeffer_group$\\Yue Zhang\\CaData\\", **kwargs):

        super(DataWrapper, self).__init__(*args, **kwargs)
        assert trigger_minion is not None, "trigger_minion must be specified"
        self._master_minion = trigger_minion

        assert remote_IP_address is not None, "remote_IP_address must be specified"
        self._remote_IP_add = remote_IP_address

        self._remote_dir = remote_dir
        self._netdrive_dir = netdrive_dir
        self._ssh = None
        self._connected = False
        self.info('Waiting for remote connection info....')

    def _connect_remote_PC(self, usr, pwd):
        err = 0
        try:
            self._ssh = paramiko.SSHClient()
            self._ssh.load_system_host_keys()
            self._ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self._ssh.connect(self._remote_IP_add, username=usr, password=pwd)
            netdrive_root = self._netdrive_dir.split('$')[0]+'$'
            _, stout, sterr = self._ssh.exec_command(f'net use \"{netdrive_root}\"')
            if sterr.channel.recv_exit_status() != 0:
                self.error(sterr.channel.recv_stderr(1000).decode('utf-8'))
            else:
                self.info(stout.channel.recv(1000).decode('utf-8'))
                self._connected = True
        except Exception as e:
            self.error(e)
            err = 1

        if err != 0:
            self.error('Failed to connect to remote PC, terminating the proces.....')
            self._on_close()

    def on_time(self, t):
        self.get(self._master_minion)
        time.sleep(0.1)

    def on_close(self):
        if self._ssh is not None:
            self._ssh.close()


    def parse_msg(self, msg_type, msg):
        if msg_type == 'data':
            if self._connected:
                local_data_dir = msg[0]
                animal_id = msg[1]
                remote_session_num = msg[2]
                self.info(f"Data wrapping request received; local_data_dir: {local_data_dir}, remote_session_num: {remote_session_num}")
                self.info("Waiting for the minion to finish saving and close the files...")
                time.sleep(2)  # Wait for the minion to finish saving and close the files
                err_code = self._dump_data_to_netdrive(local_data_dir, animal_id, remote_session_num)
                if err_code == 0:
                    self.info(f"Data saved to {self._netdrive_dir}")
                else:
                    self.error(f"Data save failed")
        elif msg_type == 'connect':
            usr,pwd = msg
            self.info(f"Remote connection info received")
            self._connect_remote_PC(usr,pwd)
        else:
            self.error(f"Unknown msg_type: {msg_type}")

    def _dump_data_to_netdrive(self, local_data_dir, animal_id, remote_session_num):
        self.info('Transferring stimulus and Aux data to the netdrive...')
        netdrive_session_dir, err_code = self._dump_local_data(local_data_dir, animal_id)
        if err_code == 0:
            self.info('Stimulus and Aux data have been copied to the netdrive...')
            self.info(f'Get Ca Data file list from remote PC... (session num: {remote_session_num})')
            remote_file_list,err_code = self._get_remote_file_list(self._remote_dir, remote_session_num)
            if err_code == 0:
                for f in remote_file_list:
                    _, stout, sterr = self._ssh.exec_command(f'COPY \"{self._remote_dir}\\{f}\" \"{netdrive_session_dir}\"')
                    if sterr.channel.recv_exit_status() != 0:
                        self.error(f'Failed to copy Ca Data file {f}')
                        self.error(sterr.channel.recv_stderr(1000).decode('utf-8'))
                        err_code = 1
                    else:
                        self.info(f'Ca Data file {f} has been copied to the netdrive')
                self.info('All data have been copied to the netdrive')
            else:
                self.error('Error in copying Ca Data')
        else:
            self.error('Error in copying stimulus and Aux data to the netdrive, abort copying Ca Data')
        return err_code

    def _dump_local_data(self, local_data_dir, animal_id):
        err_code = 1 if not os.path.isdir(local_data_dir) else 0
        if err_code == 0:
            err_code = 1 if not os.path.isdir(self._netdrive_dir) else 0
        if err_code == 0:
            err_code = self._wrap_local_data(local_data_dir)
        if err_code == 0:
            save_dir = os.path.join(self._netdrive_dir,animal_id)
            if not os.path.isdir(save_dir):
                os.mkdir(save_dir)
            netdrive_session_dir = os.path.join(save_dir,os.path.basename(local_data_dir))
            shutil.copytree(local_data_dir,netdrive_session_dir)
        return netdrive_session_dir, err_code

    def _wrap_local_data(self, fdir):
        stem_csv_fn_pattern = '_SCAN.csv'
        csv_file_list = [i for i in os.listdir(fdir) if i.endswith('.csv')]
        stem_csv_fn = [i for i in csv_file_list if i.endswith(stem_csv_fn_pattern)]
        if len(stem_csv_fn) != 1:
            self.error('Error in wrapping local csv file: multiple SCAN.csv files found')
            return -1
        else:
            stem_csv_fn = stem_csv_fn[0]
            csv_file_list.remove(stem_csv_fn)

        stem_csv = pd.read_csv(fdir + '/' + stem_csv_fn, index_col='Time')
        csv_files = [pd.read_csv(fdir + '/' + i, index_col='Time') for i in csv_file_list]
        merged = stem_csv.join(csv_files[0]).fillna(method='ffill')
        for i in range(1, len(csv_files)):
            merged = merged.join(csv_files[i]).fillna(method='ffill')
        merged = merged.drop(columns='SCAN_timestamp', axis=1)
        merged = merged.drop_duplicates()
        merged.to_csv(fdir + '/' + stem_csv_fn[:-len(stem_csv_fn_pattern)] + '_UNIFIED.csv')
        return 0

    def _get_remote_file_list(self, remote_data_dir, remote_session_num):
        sftp = self._ssh.open_sftp()
        flist = [i for i in sftp.listdir(remote_data_dir) if f'exp{remote_session_num}_ch' in i]
        sftp.close()
        if len(flist) < 0:
            self.error('Error in getting remote file list: no file found')
            return flist, -1
        else:
            return flist, 0



# class DataIOApp(AbstractAPP):
#     def __init__(self, *args, timer_minion=None, state_dict={}, buffer_dict={}, buffer_saving_opt={}, trigger=None, **kwargs):
#         super(DataIOApp, self).__init__(*args, **kwargs)
#         self._param_to_compiler = {
#             "state_dict": state_dict,
#             "buffer_dict": buffer_dict,
#             "buffer_saving_opt": buffer_saving_opt,
#             "trigger": trigger,
#             "ts_minion_name": timer_minion
#         }
#
#     def initialize(self):
#         super().initialize()
#         self._compiler = IOStreamingCompiler(self, **self._param_to_compiler)
#         self.info("Aux IO initialized.")
#
# class CamApp(AbstractAPP):
#     def __init__(self, *args, camera_name=None, save_option='binary', **kwargs):
#         super(CamApp, self).__init__(*args, **kwargs)
#         self._param_to_compiler['camera_name'] = camera_name
#         self._param_to_compiler['save_option'] = save_option
#
#     def initialize(self):
#         super().initialize()
#         self._compiler = TISCameraCompiler(self, **self._param_to_compiler, )
#         self.info("Camera Interface initialized.")
#
# class OMSInterfaceApp(AbstractAPP):
#     def __init__(self, name, compiler, timer_minion = None, trigger_minion = None, VID=None, PID=None, mw_size=1, **kwargs):
#         super(OMSInterfaceApp, self).__init__(*args, **kwargs)
#         self.timer_minion = timer_minion
#         self.trigger_minion = trigger_minion
#         self._VID = VID
#         self._PID = PID
#         self._mw_size = mw_size
#
#     def initialize(self):
#         super().initialize()
#         self._compiler = OMSInterface(self,timer_minion=self.timer_minion, trigger_minion=self.trigger_minion,
#                                       VID=self._VID, PID=self._PID, mw_size=self._mw_size)
#         self.info("OMS compiler initialized.")
#
#
# class ScanListenerApp(AbstractAPP):
#     def __init__(self, *args, timer_minion = None, trigger_minion = None, port_name=None, **kwargs):
#         super(ScanListenerApp, self).__init__(*args, **kwargs)
#         self.timer_minion = timer_minion
#         self.trigger_minion = trigger_minion
#         self._param_to_compiler = {'port_name': port_name}
#
#     def initialize(self):
#         super().initialize()
#         self._compiler = ScanListener(self, timer_minion=self.timer_minion, trigger_minion=self.trigger_minion,
#                                       **self._param_to_compiler)
#         self.info("Scan Listener initialized.")
#
#
# class PololuServoApp(AbstractAPP):
#     def __init__(self, *args, timer_minion = None, trigger_minion = None, port_name='COM6', servo_dict={}, **kwargs):
#         super(PololuServoApp, self).__init__(*args, **kwargs)
#         self.timer_minion = timer_minion
#         self.trigger_minion = trigger_minion
#         self._param_to_compiler['port_name'] = port_name
#         self._param_to_compiler['servo_dict'] = servo_dict
#
#     def initialize(self):
#         super().initialize()
#         self._compiler = PololuServoInterface(self, timer_minion=self.timer_minion, trigger_minion=self.trigger_minion,
#                                               **self._param_to_compiler, )
#         self.info("Pololu compiler initialized.")
#
#
