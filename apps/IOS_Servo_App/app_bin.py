import csv
import os

import cv2

from bin.app import AbstractGUIAPP, AbstractAPP
import time
import traceback

import PyQt5.QtWidgets as qw
import PyQt5.QtGui as qg
import PyQt5.QtCore as qc

from bin.compiler import AbstractCompiler, QtCompiler
from bin.gui import DataframeTable
from src.tisgrabber import tisgrabber as tis


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
                frame = self.get_buffer_from(mi, self._camera_param[camName]['buffer_name'])
                if frame is not None:
                    self._videoStreams[camName][1].setPixmap(
                        qg.QPixmap.fromImage(qg.QImage(frame, frame.shape[1], frame.shape[0], frame.strides[0],
                                                       qg.QImage.Format_RGB888)))
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


class IOStreamingCompiler(AbstractCompiler):

    def __init__(self, *args, state_dict={}, buffer_dict={}, buffer_saving_opt={}, trigger=None, **kwargs):
        '''
        A compiler for the IOHandler class that receives and save all data from its connected minions.
        :param state_dict: a dictionary whose keys will be the names of the minions and the values will be lists of parameters to save in a csv file.
        :param buffer_dict: a dictionary whose keys will be the names of the minions and the values will be lists of buffers to save.
        :param buffer_saving_opt: a dictionary whose keys will be the names of the minions and the values will be option dictionaries. The key of the option dictionary is the name of the buffer and the value is the saving options.
        :param trigger: the name of a foreign state whose change will trigger the saving of all data.
        '''
        super().__init__(*args, **kwargs)
        self.state_dict = state_dict
        self.buffer_dict = buffer_dict
        self.buffer_saving_opt = buffer_saving_opt
        self._trigger_state_name = trigger
        self.trigger = None

        # Initializing saving handler
        self._state_stream_fn = None
        self._state_stream_handler = None
        self._state_stream_writer = None
        self._buffer_handle_param = {}
        self._buffer_streaming_handle = {}
        self._streaming_start_time = 0
        self.streaming = False

        for mi_name, buf_name in self.buffer_dict.items():
            self._buffer_streaming_handle[mi_name] = {}
            for i_buf in buf_name:
                if self.buffer_saving_opt.get(mi_name) is not None:
                    opt = self.buffer_saving_opt[mi_name].get('i_buf')
                else:
                    opt = None
                self._buffer_streaming_handle[mi_name][i_buf] = (None, opt)

        # Initializing saving parameters and create the corresponding shared state to receive GUI control
        self.saving_param = {'StreamToDisk': False,
                             'SaveDir': None,
                             'SaveName': None,
                             'InitTime': None}

        for k, v in self.saving_param.items():
            self.create_state(k, v)

    def add_streaming_state(self, mi_name, state_name):
        if self.state_dict.get(mi_name) is None:
            self.state_dict[mi_name] = [state_name]
            self.info('Created streaming state list for {} and added {} to the list'.format(mi_name, state_name))
        else:
            if state_name not in self.state_dict[mi_name]:
                self.state_dict[mi_name].append(state_name)
                self.info('Added {} to the streaming state list of {}'.format(state_name, mi_name))
            else:
                self.error('{} is already in the streaming state list of {}'.format(state_name, mi_name))

    def remove_streaming_state(self, mi_name, state_name):
        if self.state_dict.get(mi_name) is not None:
            if state_name in self.state_dict[mi_name]:
                self.state_dict[mi_name].remove(state_name)
                self.info('Removed {} from the streaming state list of {}'.format(state_name, mi_name))
            else:
                self.error('{} is not in the streaming state list of {}'.format(state_name, mi_name))
        else:
            self.error('{} is not registered for streaming'.format(mi_name))

    def add_streaming_buffer(self, mi_name, buffer_name, saving_opt=None):
        if self.buffer_dict.get(mi_name) is None:
            self.buffer_dict[mi_name] = [buffer_name]
            self._buffer_streaming_handle[mi_name][buffer_name] = (None, saving_opt)
            self.info('Created streaming buffer list for {} and added {} to the list'.format(mi_name, buffer_name))
        else:
            if buffer_name not in self.buffer_dict[mi_name]:
                self.buffer_dict[mi_name].append(buffer_name)
                self._buffer_streaming_handle[mi_name][buffer_name] = (None, saving_opt)
                self.info('Added {} to the streaming buffer list of {}'.format(buffer_name, mi_name))
            else:
                self.info('{} is already in the streaming buffer list of {}'.format(buffer_name, mi_name))

    def remove_streaming_buffer(self, mi_name, buffer_name):
        if self.buffer_dict.get(mi_name) is not None:
            if buffer_name in self.buffer_dict[mi_name]:
                self.buffer_dict[mi_name].remove(buffer_name)
                self._buffer_streaming_handle[mi_name].pop(buffer_name)
                self.info('Removed {} from the streaming buffer list of {}'.format(buffer_name, mi_name))
            else:
                self.error('{} is not in the streaming buffer list of {}'.format(buffer_name, mi_name))
        else:
            self.error('{} is not registered for streaming'.format(mi_name))

    def _streaming_setup(self):
        if_streaming = self.get_state('StreamToDisk')
        if self.watch_state('StreamToDisk', if_streaming):  # Triggered at the onset and the end of streaming
            if if_streaming:
                err = self._prepare_streaming()
                if not err:
                    self._start_streaming()
            else:  # close all files before streaming stops
                self._stop_streaming()

    def _prepare_streaming(self):
        err = False
        missing_state_list = []
        missing_buffer_list = []
        stateStreamHandlerFn = None
        bufferHandlerParam = {}

        # Check if all the shared states and buffers are available
        for mi_name, state_name in self.state_dict.items():
            i_state_dict = self.get_state_from(mi_name, 'ALL')
            for i_state in state_name:
                if i_state_dict.get(i_state) is None:
                    missing_state_list.append((mi_name, i_state))

        for mi_name, buffer_name in self.buffer_dict.items():
            bufferHandlerParam[mi_name] = {}
            for i_buf in buffer_name:
                buf_val = self.get_state_from(mi_name, i_buf)
                if buf_val is None:
                    missing_buffer_list.append((mi_name, i_buf))
                else:
                    bufferHandlerParam[mi_name][i_buf] = {}
                    bufferHandlerParam[mi_name][i_buf]['shape'] = buf_val.shape

        if len(missing_state_list) > 0:
            err = True
            self.error("Streaming could not start because the shared state(s) cannot be found:\n {}".format(
                missing_state_list))
        if len(missing_buffer_list) > 0:
            err = True
            self.error("Streaming could not start because the shared buffer(s) cannot be found:\n {}".format(
                missing_buffer_list))

        # Check if all the saving parameters are defined
        if not err:
            save_dir = self.get_state('SaveDir')
            file_name = self.get_state('SaveName')
            start_time = self.get_state('InitTime')
            missing_saving_param = [i for i in [save_dir, file_name, start_time] if i is None]
            if len(missing_saving_param) > 0:
                err = True
                self.error("Streaming could not start because of the following undefined parameter(s): {}".format(
                    missing_saving_param))

        # Check if the save directory exists and any file with the same name already exists
        if not err:
            if os.path.isdir(save_dir):
                stateStreamHandlerFn = os.path.join(save_dir, f"{file_name}.csv")
                if os.path.isfile(stateStreamHandlerFn):
                    err = True
                    self.error("Streaming could not start because the state csv file {} already exists".format(
                        stateStreamHandlerFn))

                errFnList = []
                for mi, i_buf in self._buffer_streaming_handle.items():
                    for buf_name, v in i_buf.items():
                        if v[1] is None or v[1] == 'binary':
                            BIN_Fn = os.path.join(save_dir, f"{file_name}_{mi}_{buf_name}.bin")
                            if os.path.isfile(BIN_Fn):
                                errFnList.append(f"{file_name}_{mi}_{buf_name}.bin")
                                err = True
                            else:
                                bufferHandlerParam[mi][buf_name]['type'] = 'binary'
                                bufferHandlerParam[mi][buf_name]['fn'] = BIN_Fn
                        elif v[1] == 'movie':
                            BIN_Fn = os.path.join(save_dir, f"{file_name}_{mi}_{buf_name}.avi")
                            if os.path.isfile(BIN_Fn):
                                errFnList.append(f"{file_name}_{mi}_{buf_name}.avi")
                                err = True
                            else:
                                bufferHandlerParam[mi][buf_name]['type'] = 'movie'
                                bufferHandlerParam[mi][buf_name]['fn'] = BIN_Fn

                if len(errFnList) > 0:
                    self.error("Streaming could not start because the following buffer files already exist: {}".format(
                        errFnList))
                    err = True
            else:
                err = True
                self.error("Streaming could not start because the save directory {} does not exist".format(save_dir))

        if not err:
            self._state_stream_fn = stateStreamHandlerFn
            self._bufferHandlerParam = bufferHandlerParam

        return err

    def _start_streaming(self):
        # Create the state csv file
        self._state_stream_handler = open(self._state_stream_fn, 'w', newline='')
        self._state_stream_writer = csv.writer(self._state_stream_handler)
        name_row = ['Time']
        for mi_name, state_name in self.state_dict.items():
            for i_state in state_name:
                name_row.append(f"{mi_name}_{i_state}")
        self._state_stream_writer.writerow(name_row)

        # Create the buffer files
        for mi, i_buf in self._buffer_streaming_handle.items():
            for buf_name, v in i_buf.items():
                fn = self._bufferHandlerParam[mi][buf_name]['fn']
                fshape = self._bufferHandlerParam[mi][buf_name]['shape']
                if v[1] is None or v[1] == 'binary':
                    self._buffer_streaming_handle[mi][buf_name] = (open(fn, 'wb'), v[1])
                elif v[1] == 'movie':
                    self._buffer_streaming_handle[mi][buf_name] = (cv2.VideoWriter(fn, cv2.VideoWriter_fourcc(*'MJPG'),
                                                                                   int(1000/self.refresh_interval),
                                                                                   fshape),
                                                                   'movie')

        start_time = self.get_state('InitTime')
        self._streaming_start_time = start_time
        self.streaming = True

    def _stop_streaming(self):
        if self.streaming:
            self.streaming = False
            self._state_stream_handler.close()
            for mi, i_buf in self._buffer_streaming_handle.items():
                for buf_name, v in i_buf.items():
                    if v[1] is None or v[1] == 'binary':
                        v[0].close()
                    elif v[1] == 'movie':
                        v[0].release()

            self._state_stream_fn = None
            self._state_stream_handler = None
            self._state_stream_writer = None
            self._buffer_handle_param = {}
            self._buffer_streaming_handle = {}
            self._streaming_start_time = 0
            self.streaming = False

    def _streaming(self):
        if self.streaming:
            # Write to state csv file
            trigger = None
            mi, st = self._trigger_state_name.split('_')
            trigger_state = self.get_state_from(mi, st)
            if trigger_state is not None:
                trigger = self.watch_state('Trigger', trigger_state)
            if trigger:
                t = time.perf_counter() - self._stream_init_time
                val_row = [t]
                for mi_name, state_name in self.state_dict.items():
                    state_dict = self.get_state_from(mi_name, 'ALL')
                    for i_state in state_name:
                        val_row.append(state_dict[i_state])
                self._state_stream_writer.writerow(val_row)

                for mi, i_buf in self._buffer_streaming_handle.items():
                    for buf_name, v in i_buf.items():
                        if v[1] is None or v[1] == 'binary':
                            self._buffer_streaming_handle[mi][buf_name].write(bytearray(self.get_buffer_from(mi, buf_name)))
                        elif v[1] == 'movie':
                            self._buffer_streaming_handle[mi][buf_name].write(self.get_buffer_from(mi, buf_name))

    def on_time(self, t):
        self._streaming_setup()
        self._streaming()