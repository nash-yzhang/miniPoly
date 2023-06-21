import os

from bin.app.prototypes import AbstractGUIAPP, AbstractAPP
import time
import traceback

import PyQt5.QtWidgets as qw
import PyQt5.QtGui as qg

from bin.compiler.graphics import QtCompiler
from bin.compiler.serial_devices import PololuServoInterface, ArduinoCompiler
from bin.gui import DataframeTable
from src.tisgrabber import tisgrabber as tis


class CameraGUI(QtCompiler):

    def __init__(self, *args, **kwargs):
        super(CameraGUI, self).__init__(*args, **kwargs)
        self._camera_minions = [i for i in self.get_linked_minion_names() if 'tiscam' in i.lower()]
        self._connected_camera_minions = {}
        self._camera_param = {}
        self._videoStreams = {}
        self.camconfig_videoFormat_list_idx = None

        self._root_folder = None
        self._save_camera_list = []

        self._tiscamHandle = tis.TIS_CAM()

        self._deviceList = self._tiscamHandle.GetDevices()

        self._init_main_window()
        self._init_menu()

    def _init_main_window(self):
        self.layout_main = qw.QVBoxLayout()
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

        self.layout_main.addLayout(self.layout_CamView)
        self.layout_main.addLayout(self.layout_SavePanel)
        self.main_widget = qw.QWidget()
        self.main_widget.setLayout(self.layout_main)
        self.setCentralWidget(self.main_widget)

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

        else:
            self._save_btn.setText('Start Recording')
            self._save_btn.setStyleSheet('background-color: white')
            for cam in self._save_camera_list:
                mi_name = self._connected_camera_minions[cam]
                self.set_state_to(mi_name, 'StreamToDisk', False)

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
            self.error('Camera not connected')
        else:
            self.set_state_to(self._connected_camera_minions[cameraName], 'CameraName', None)
            self._connected_camera_minions.pop(cameraName)
            if not saveConfig:
                self._camera_param.pop(cameraName)
            if not saveGUI:
                self.layout_CamView.removeWidget(self._videoStreams[cameraName][0])
                self._videoStreams.pop(cameraName)

    def refresh(self, cameraName):
        self._disconnect_camera(cameraName, saveConfig=True, saveGUI=True)
        time.sleep(.5)
        self._connect_camera(cameraName)

    def setupCameraFrameGUI(self, cameraName):
        self._videoStreams[cameraName] = [qw.QWidget(),
                                          qw.QLabel(cameraName),
                                          qw.QPushButton('Refresh'),
                                          qw.QLabel('Save: '),
                                          qw.QCheckBox('Save')]
        cameraWidget = self._videoStreams[cameraName][0]
        camNameLabel = self._videoStreams[cameraName][1]
        refresh_btn = self._videoStreams[cameraName][2]
        save_label = self._videoStreams[cameraName][3]
        save_checkbox = self._videoStreams[cameraName][4]

        layout = qw.QVBoxLayout()
        self._videoStreams[cameraName][1].setPixmap(qg.QPixmap())
        sublayout = qw.QHBoxLayout()
        refresh_btn.clicked.connect(lambda: self.refresh(cameraName))
        sublayout.addWidget(refresh_btn)
        sublayout.addWidget(save_label)
        sublayout.addWidget(save_checkbox)

        layout.addWidget(camNameLabel)
        layout.addLayout(sublayout)
        cameraWidget.setLayout(layout)
        self.layout_CamView.addWidget(cameraWidget)

    def on_time(self, t):
        for camName, mi in self._connected_camera_minions.items():
            try:
                frame = self.get_buffer_from(mi, self._camera_param[camName]['buffer_name'])
                if frame is not None:
                    self._videoStreams[camName][1].setPixmap(
                        qg.QPixmap.fromImage(qg.QImage(frame, frame.shape[1], frame.shape[0], frame.strides[0],
                                                       qg.QImage.Format_RGB888)))
            except:
                self.debug('Error when trying to get frame from camera minion.')
                self.debug(traceback.format_exc())
        self._processHandler.on_time(t)


class CameraStimGUI(QtCompiler):
    _SERVO_MIN = 2400
    _SERVO_MAX = 9000

    def __init__(self, *args, **kwargs):
        super(CameraStimGUI, self).__init__(*args, **kwargs)
        self._camera_minions = [i for i in self.get_linked_minion_names() if 'tiscam' in i.lower()]
        self._connected_camera_minions = {}
        self._camera_param = {}
        self._videoStreams = {}
        self.camconfig_videoFormat_list_idx = None

        self._root_folder = None
        self._save_camera_list = []

        self._tiscamHandle = tis.TIS_CAM()

        self._deviceList = self._tiscamHandle.GetDevices()

        self._servo_minion = [i for i in self.get_linked_minion_names() if 'servo' in i.lower()]
        self._serial_minion = [i for i in self.get_linked_minion_names() if 'serial' in i.lower()]

        self._init_main_window()
        self._init_menu()

    def _init_main_window(self):
        self.layout_main = qw.QVBoxLayout()
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

        self.layout_main.addLayout(self.layout_CamView)
        self.layout_main.addLayout(self.layout_SavePanel)
        self.layout_main.addLayout(self.layout_stimGUI)

        self.main_widget = qw.QWidget()
        self.main_widget.setLayout(self.layout_main)
        self.setCentralWidget(self.main_widget)

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
            self.error('Camera not connected')
        else:
            self.set_state_to(self._connected_camera_minions[cameraName], 'CameraName', None)
            self._connected_camera_minions.pop(cameraName)
            if not saveConfig:
                self._camera_param.pop(cameraName)
            if not saveGUI:
                self.layout_CamView.removeWidget(self._videoStreams[cameraName][0])
                self._videoStreams.pop(cameraName)

    def refresh(self, cameraName):
        self._disconnect_camera(cameraName, saveConfig=True, saveGUI=True)
        time.sleep(.5)
        self._connect_camera(cameraName)

    def setupCameraFrameGUI(self, cameraName):
        self._videoStreams[cameraName] = [qw.QWidget(),
                                          qw.QLabel(cameraName),
                                          qw.QPushButton('Refresh'),
                                          qw.QLabel('Save: '),
                                          qw.QCheckBox('Save')]
        cameraWidget = self._videoStreams[cameraName][0]
        camNameLabel = self._videoStreams[cameraName][1]
        refresh_btn = self._videoStreams[cameraName][2]
        save_label = self._videoStreams[cameraName][3]
        save_checkbox = self._videoStreams[cameraName][4]

        layout = qw.QVBoxLayout()
        self._videoStreams[cameraName][1].setPixmap(qg.QPixmap())
        sublayout = qw.QHBoxLayout()
        refresh_btn.clicked.connect(lambda: self.refresh(cameraName))
        sublayout.addWidget(refresh_btn)
        sublayout.addWidget(save_label)
        sublayout.addWidget(save_checkbox)

        layout.addWidget(camNameLabel)
        layout.addLayout(sublayout)
        cameraWidget.setLayout(layout)
        self.layout_CamView.addWidget(cameraWidget)

    def on_time(self, t):
        for camName, mi in self._connected_camera_minions.items():
            try:
                frame = self.get_state_from(mi, self._camera_param[camName]['buffer_name'])
                if frame is not None:
                    self._videoStreams[camName][1].setPixmap(
                        qg.QPixmap.fromImage(qg.QImage(frame[:,:,0], frame.shape[1], frame.shape[0], frame.strides[0],
                                                       qg.QImage.Format_Grayscale8)))
            except:
                self.debug('Error when trying to get frame from camera minion.')
                self.debug(traceback.format_exc())
        self._processHandler.on_time(t)

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


class CameraInterface(AbstractGUIAPP):
    def __init__(self, *args, **kwargs):
        super(CameraInterface, self).__init__(*args, **kwargs)

    def initialize(self):
        super().initialize()
        self._win = CameraStimGUI(self)
        self.info("Camera Interface initialized.")
        self._win.show()


class PololuServoApp(AbstractAPP):
    def __init__(self, *args, port_name='COM6', servo_dict={}, **kwargs):
        super(PololuServoApp, self).__init__(*args, **kwargs)
        self._param_to_compiler['port_name'] = port_name
        self._param_to_compiler['servo_dict'] = servo_dict

    def initialize(self):
        super().initialize()
        self._compiler = PololuServoInterface(self, **self._param_to_compiler, )
        self.info("Pololu compiler initialized.")


class ArduinoApp(AbstractAPP):
    def __init__(self, *args, port_name='COM6', pin_address={}, **kwargs):
        super(ArduinoApp, self).__init__(*args, **kwargs)
        self._param_to_compiler['port_name'] = port_name
        self._param_to_compiler['pin_address'] = pin_address

    def initialize(self):
        super().initialize()
        self._compiler = ArduinoCompiler(self, **self._param_to_compiler, )
        self.info("Arduino Compiler initialized.")
