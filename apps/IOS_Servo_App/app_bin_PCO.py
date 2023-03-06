import csv
import ctypes
import os

import cv2
import numpy as np
import pandas as pd
import serial

from bin.app import AbstractGUIAPP, AbstractAPP
import time
import traceback

import PyQt5.QtWidgets as qw
import PyQt5.QtGui as qg
import PyQt5.QtCore as qc
import PyQt5.Qt


from vispy import scene
from vispy.io import load_data_file, read_png

from bin.compiler import AbstractCompiler, QtCompiler
from bin.gui import DataframeTable

import pco

import pyfirmata as fmt

class CameraStimGUI(QtCompiler):
    _SERVO_MIN = 2400
    _SERVO_MAX = 9000

    def __init__(self, *args, **kwargs):
        super(CameraStimGUI, self).__init__(*args, **kwargs)

        self._stimulus_minion = 'Stimulus'
        self._IO_minion = 'IO'
        self._stimulusFn_forwarded = False

        self._camera_minions = [i for i in self.get_linked_minion_names() if 'pcocam' in i.lower()]
        self._connected_camera_minions = {}
        self._camera_param = {}
        self._videoStreams = {}
        self._connected = False

        self._root_folder = None
        self._save_camera_list = []

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

            self.set_state_to(self._IO_minion,'SaveDir', self._save_dir)
            self.set_state_to(self._IO_minion,'SaveName', self._save_filename)
            self.set_state_to(self._IO_minion,'InitTime', self._save_init_time)
            self.set_state_to(self._IO_minion,'StreamToDisk', True)

        else:
            self._save_btn.setText('Start Recording')
            self._save_btn.setStyleSheet('background-color: white')
            for cam in self._save_camera_list:
                mi_name = self._connected_camera_minions[cam]
                self.set_state_to(mi_name, 'StreamToDisk', False)
            self.set_state_to(self._IO_minion,'StreamToDisk', False)

    def _init_menu(self):
        self._menubar = self.menuBar()
        self._menu_file = self._menubar.addMenu('File')

        self.CamConn = qw.QAction("Connect Camera", self)
        self.CamConn.setShortcut("Ctrl+O")
        self.CamConn.setStatusTip("Connect PCO Camera")
        self.CamConn.triggered.connect(self.cam_conn)

        self.loadStim = qw.QAction("Load Stim File", self)
        self.loadStim.setShortcut("Ctrl+Shift+F")
        self.loadStim.setStatusTip("Load Stimulus xlsx file")
        self.loadStim.triggered.connect(self.load_file)

        Exit = qw.QAction("Quit", self)
        Exit.setShortcut("Ctrl+Q")
        Exit.setStatusTip("Exit program")
        Exit.triggered.connect(self.close)

        self._menu_file.addAction(self.CamConn)
        self._menu_file.addAction(self.loadStim)
        self._menu_file.addAction(Exit)

    def load_file(self):
        self._stimulusFn = qw.QFileDialog.getOpenFileName(self, 'Open file', '.', "stimulus protocol (*.xlsx)", options= qw.QFileDialog.DontUseNativeDialog)[0]
        if self.tables['Protocol'] is not None:
            self.tables['Protocol'].loadfile(self._stimulusFn)
            self.tables['Protocol'].filename = self._stimulusFn

    def cam_conn(self):
        if self._connected:
            self.disconnect_camera()
            self._connected = False
            self.CamConn.setText("Connect Camera")
            self.CamConn.setStatusTip("Connect PCO Camera")
        else:
            self.connect_camera()
            self._connected = True
            self.CamConn.setText("Disconnect Camera")
            self.CamConn.setStatusTip("Remove PCO Camera")

    def connect_camera(self):
        cameraName = 'PCO'
        self._camera_param[cameraName] = {
            'VideoFormat': None,
            'StreamToDisk': None,
            'SaveDir': None,
            'SaveName': None,
            'InitTime': None,
        }
        hasGUI = cameraName in self._connected_camera_minions.keys()
        if not hasGUI:
            self.setupCameraFrameGUI(cameraName)
        self.camconfig_videoFormat_list_idx = 0

        if cameraName in self._connected_camera_minions.keys():
            self.error('Camera already connected')
        else:
            free_minion = [i for i in self._camera_minions if i not in self._connected_camera_minions.values()]
            if not free_minion:
                self.error('No more camera minion available')
            else:
                mi = free_minion[0]
                self.set_state_to(mi, 'CameraName', cameraName)
                self._camera_param[cameraName]['buffer_name'] = "frame_PCO_cam"
                self._connected_camera_minions[cameraName] = mi


        time.sleep(5)


    def disconnect_camera(self, saveConfig=False, saveGUI=False):
        cameraName = 'PCO'
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
        self.disconnect_camera(saveConfig=True, saveGUI=True)
        time.sleep(.5)
        self.connect_camera()

    def setupCameraFrameGUI(self, cameraName):
        self._videoStreams[cameraName] = [qw.QWidget(),
                                          None,
                                          qw.QPushButton('Refresh'),
                                          qw.QLabel('Save: '),
                                          qw.QCheckBox('Save')]
        cameraWidget = self._videoStreams[cameraName][0]
        refresh_btn = self._videoStreams[cameraName][2]
        save_label = self._videoStreams[cameraName][3]
        save_checkbox = self._videoStreams[cameraName][4]

        layout = qw.QVBoxLayout()
        self._videoStreams[cameraName][1] = self._setup_scene_canvas()
        sublayout = qw.QHBoxLayout()
        refresh_btn.clicked.connect(lambda: self.refresh(cameraName))
        sublayout.addWidget(refresh_btn)
        sublayout.addWidget(save_label)
        sublayout.addWidget(save_checkbox)

        layout.addWidget(self._videoStreams[cameraName][1].native)
        layout.addLayout(sublayout)
        cameraWidget.setLayout(layout)
        self.layout_CamView.addWidget(cameraWidget)

    def _setup_scene_canvas(self):

        canvas = scene.SceneCanvas(keys='interactive')
        canvas.size = 800, 600

        # Set up a viewbox to display the image with interactive pan/zoom
        view = canvas.central_widget.add_view()

        # Create the image
        img_data = read_png(load_data_file('mona_lisa/mona_lisa_sm.png'))
        interpolation = 'nearest'

        self._image_handle = scene.visuals.Image(img_data, interpolation=interpolation,
                                    parent=view.scene, method='subdivide')

        # Set 2D camera (the camera will scale to the contents in the scene)
        view.camera = scene.PanZoomCamera(aspect=1)
        # flip y-axis to have correct aligment
        view.camera.flip = (0, 1, 0)
        view.camera.set_range()
        view.camera.zoom(0.1, (250, 200))

        return canvas

    def on_time(self, t):
        StimulusFn = self.tables['Protocol'].filename
        if self.watch_state('StimulusFn',StimulusFn) and StimulusFn is not None:
            self.set_state_to(self._stimulus_minion, 'StimulusFn', StimulusFn)
            self._stimulusFn_forwarded = True

        if StimulusFn is not None:
            if self._timer_started:
                phaseIdx = self.get_state_from(self._stimulus_minion, 'PhaseIdx')
                if phaseIdx is not None:
                    self.tables['Protocol'].selectRow(phaseIdx)

        for camName, mi in self._connected_camera_minions.items():
            try:
                frame = self.get_buffer_from(mi, self._camera_param[camName]['buffer_name'])
                if frame is not None:
                    frame = frame.astype(np.uint8)
                    self._image_handle.set_data(frame)
                    self._videoStreams['PCO'][1].update()
            except:
                self.error('Error when trying to get frame from camera minion.')
                self.error(traceback.format_exc())
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
            self.stopTimer()
        else:
            self.startTimer()

    def startTimer(self):
        self.set_state_to(self._stimulus_minion, 'is_running', True)
        self._timer_started = True
        self.timer_switcher.setText('Stop')

    def stopTimer(self):
        self.set_state_to(self._stimulus_minion, 'is_running', False)
        self._timer_started = False  # self._time = self._time.elapsed()
        self.timer_switcher.setText('Start')


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
                        else:
                            bufferHandlerParam[mi][buf_name]['type'] = 'disabled'
                            bufferHandlerParam[mi][buf_name]['fn'] = None
                            self.warning("Streaming of {} from {} is disabled".format(buf_name, mi))

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
                else:
                    self._buffer_streaming_handle[mi][buf_name] = (None, None)

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
                    else:
                        pass

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
            trigger = True
            if self._trigger_state_name:
                mi, st = self._trigger_state_name.split('_')
                trigger_state = self.get_state_from(mi, st)
                if trigger_state is not None:
                    trigger = self.watch_state('Trigger', trigger_state)
            if trigger:
                t = time.perf_counter() - self._streaming_start_time
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
                        else:
                            pass

    def on_time(self, t):
        self._streaming_setup()
        self._streaming()

class LightSaberStmulusCompiler(AbstractCompiler):

    _SERVO_MIN = 2500
    _SERVO_MAX = 10000

    def __init__(self, *args, servo_port_name, arduino_port_name, servo_dict, arduino_dict, **kwargs):
        super(LightSaberStmulusCompiler, self).__init__(*args, **kwargs)

        self._arduino_port_name = arduino_port_name
        self._arduino_port = None
        self.arduino_dict = arduino_dict
        self._arduino_pin_address = {}

        self._servo_port_name = servo_port_name
        self._servo_port = None
        self.servo_dict = servo_dict

        self.is_running = False

        self.stimulus_fn = None
        self.stimulus_phase_idx = 0
        self.stimulus_phase_num = 0
        self.create_state('is_running', False)
        self.create_state('StimulusFn', 0)
        self.create_state('PhaseIdx', self.stimulus_phase_idx)
        self.create_state('TotalPhase', self.stimulus_phase_num)

        self.init_pololu()
        self.init_arduino()

    def on_time(self, t):
        try:
            self._stimulus_setup()
            self._exec_stim()
        except:
            self.error('Error in running stimulus')
            self.error(traceback.format_exc())

    def _stimulus_setup(self):
        is_running = self.get_state('is_running')
        if self.watch_state('is_running', is_running) and is_running is not None:
            if is_running:
                self._start_stimulus()
            else:
                self._stop_stimulus()

    def _start_stimulus(self):
        # Check if the stimulus file has changed
        self.stimulusFn = self.get_state('StimulusFn')
        if self.stimulusFn is not None:
            can_start = self._load_stimulus_table(self.stimulusFn)
            if can_start:
                self._init_time = time.perf_counter()
                self.is_running = True
            else:
                self.error('Cannot run stimulus because of the errors in loading stimulus protocol file')

    def _load_stimulus_table(self, fn):
        can_start_stimulus = False
        if os.path.isfile(fn):
            if os.path.splitext(fn)[1] in ['.xls', '.xlsx']:
                _stimulus_table = pd.read_excel(fn)
                _stimulus_param = [i for i in _stimulus_table.columns]
                missing_servo_param = [i for i in self.servo_dict.keys() if i not in _stimulus_param]
                missing_arduino_param = [i for i in self.arduino_dict.keys() if i not in _stimulus_param]
                if (len(missing_arduino_param)+len(missing_servo_param) == 0) and 'Time' in _stimulus_param:
                    self._stimulus_table = _stimulus_table
                    self.stimulus_phase_num = self._stimulus_table.shape[0]
                    can_start_stimulus = True
                else:
                    self.error('Missing parameters in the stimulus protocol: {}'.format(missing_servo_param+missing_arduino_param))
            else:
                self.error('Stimulus protocol file must be a excel file')
        else:
            self.error('Stimulus protocol file does not exist')
        return can_start_stimulus

    def _stop_stimulus(self):
        self.is_running = False
        self._init_time = 0
        self.stimulus_phase_idx = 0
        self.set_state('PhaseIdx', self.stimulus_phase_idx)
        self.set_state('TotalPhase', self.stimulus_phase_num)

    def _exec_stim(self):
        if self.is_running:
            if self.stimulus_phase_idx <= self.stimulus_phase_num:
                if (time.perf_counter()-self._init_time) >= self._stimulus_table['Time'][self.stimulus_phase_idx]:
                    for n, v in self.servo_dict.items():
                        state = float(self._stimulus_table[n][self.stimulus_phase_idx])  # Make sure it's not int64 or will crash the whole program as int64 is not JSON serializable
                        abs_state = int(state * (self._SERVO_MAX - self._SERVO_MIN) + self._SERVO_MIN)
                        self.setTarget(v, abs_state)
                        self.set_state(n, state)
                    for n, v in self.arduino_dict.items():
                        state = int(self._stimulus_table[n][self.stimulus_phase_idx])  # Make sure it's not int64 or will crash the whole program as int64 is not JSON serializable
                        self._arduino_pin_address[n].write(state)
                        self.set_state(n, state)
                    self.stimulus_phase_idx += 1
                    self.set_state('PhaseIdx', self.stimulus_phase_idx)
            else:
                self._stop_stimulus()

    def on_close(self):
        self._servo_port.close()
        self._arduino_port.exit()

    def init_arduino(self):
        self._arduino_port = fmt.Arduino(self._arduino_port_name)
        for n, v in self.arduino_dict.items():
            try:
                self._arduino_pin_address[n] = self._arduino_port.get_pin(v)
                self.create_state(n, 0)
            except:
                print(traceback.format_exc())

    ###### The following are copied from https://github.com/FRC4564/Maestro/blob/master/maestro.py with MIT license
    def init_pololu(self):
        self._servo_port = serial.Serial(self._servo_port_name)
        # Command lead-in and device number are sent for each Pololu serial command.
        self.PololuCmd = chr(0xaa) + chr(0x0c)
        # Track target position for each servo. The function isMoving() will
        # use the Target vs Current servo position to determine if movement is
        # occuring.  Upto 24 servos on a Maestro, (0-23). Targets start at 0.
        self.Targets = [0] * 24
        # Servo minimum and maximum targets can be restricted to protect components.
        self.Mins = [0] * self._SERVO_MIN
        self.Maxs = [0] * self._SERVO_MAX
        for n, v in self.servo_dict.items():
            self.create_state(n, self.getPosition(v))

    def sendCmd(self, cmd):
        cmdStr = self.PololuCmd + cmd
        self._servo_port.write(bytes(cmdStr, 'latin-1'))

        # Set channels min and max value range.  Use this as a safety to protect
        # from accidentally moving outside known safe parameters. A setting of 0
        # allows unrestricted movement.
        #
        # ***Note that the Maestro itself is configured to limit the range of servo travel
        # which has precedence over these values.  Use the Maestro Control Center to configure
        # ranges that are saved to the controller.  Use setRange for software controllable ranges.

    def setRange(self, chan, min, max):
        self.Mins[chan] = min
        self.Maxs[chan] = max

        # Return Minimum channel range value

    def getMin(self, chan):
        return self.Mins[chan]

        # Return Maximum channel range value

    def getMax(self, chan):
        return self.Maxs[chan]

        # Set channel to a specified target value.  Servo will begin moving based
        # on Speed and Acceleration parameters previously set.
        # Target values will be constrained within Min and Max range, if set.
        # For servos, target represents the pulse width in of quarter-microseconds
        # Servo center is at 1500 microseconds, or 6000 quarter-microseconds
        # Typcially valid servo range is 3000 to 9000 quarter-microseconds
        # If channel is configured for digital output, values < 6000 = Low ouput

    def setTarget(self, chan, target):
        # if Min is defined and Target is below, force to Min
        if self.Mins[chan] > 0 and target < self.Mins[chan]:
            target = self.Mins[chan]
        # if Max is defined and Target is above, force to Max
        if self.Maxs[chan] > 0 and target > self.Maxs[chan]:
            target = self.Maxs[chan]
        #
        lsb = target & 0x7f  # 7 bits for least significant byte
        msb = (target >> 7) & 0x7f  # shift 7 and take next 7 bits for msb
        cmd = chr(0x04) + chr(chan) + chr(lsb) + chr(msb)
        self.sendCmd(cmd)
        # Record Target value
        self.Targets[chan] = target

        # Set speed of channel
        # Speed is measured as 0.25microseconds/10milliseconds
        # For the standard 1ms pulse width change to move a servo between extremes, a speed
        # of 1 will take 1 minute, and a speed of 60 would take 1 second.
        # Speed of 0 is unrestricted.

    def setSpeed(self, chan, speed):
        lsb = speed & 0x7f  # 7 bits for least significant byte
        msb = (speed >> 7) & 0x7f  # shift 7 and take next 7 bits for msb
        cmd = chr(0x07) + chr(chan) + chr(lsb) + chr(msb)
        self.sendCmd(cmd)

        # Set acceleration of channel
        # This provides soft starts and finishes when servo moves to target position.
        # Valid values are from 0 to 255. 0=unrestricted, 1 is slowest start.
        # A value of 1 will take the servo about 3s to move between 1ms to 2ms range.

    def setAccel(self, chan, accel):
        lsb = accel & 0x7f  # 7 bits for least significant byte
        msb = (accel >> 7) & 0x7f  # shift 7 and take next 7 bits for msb
        cmd = chr(0x09) + chr(chan) + chr(lsb) + chr(msb)
        self.sendCmd(cmd)

        # Get the current position of the device on the specified channel
        # The result is returned in a measure of quarter-microseconds, which mirrors
        # the Target parameter of setTarget.
        # This is not reading the true servo position, but the last target position sent
        # to the servo. If the Speed is set to below the top speed of the servo, then
        # the position result will align well with the acutal servo position, assuming
        # it is not stalled or slowed.

    def getPosition(self, chan):
        cmd = chr(0x10) + chr(chan)
        self.sendCmd(cmd)
        lsb = ord(self._servo_port.read())
        msb = ord(self._servo_port.read())
        return (msb << 8) + lsb

        # Test to see if a servo has reached the set target position.  This only provides
        # useful results if the Speed parameter is set slower than the maximum speed of
        # the servo.  Servo range must be defined first using setRange. See setRange comment.
        #
        # ***Note if target position goes outside of Maestro's allowable range for the
        # channel, then the target can never be reached, so it will appear to always be
        # moving to the target.

    def isMoving(self, chan):
        if self.Targets[chan] > 0:
            if self.getPosition(chan) != self.Targets[chan]:
                return True
        return False

        # Have all servo outputs reached their targets? This is useful only if Speed and/or
        # Acceleration have been set on one or more of the channels. Returns True or False.
        # Not available with Micro Maestro.

    def getMovingState(self):
        cmd = chr(0x13)
        self.sendCmd(cmd)
        if self._servo_port.read() == chr(0):
            return False
        else:
            return True

        # Run a Maestro Script subroutine in the currently active script. Scripts can
        # have multiple subroutines, which get numbered sequentially from 0 on up. Code your
        # Maestro subroutine to either infinitely loop, or just end (return is not valid).

    def runScriptSub(self, subNumber):
        cmd = chr(0x27) + chr(subNumber)
        # can pass a param with command 0x28
        # cmd = chr(0x28) + chr(subNumber) + chr(lsb) + chr(msb)
        self.sendCmd(cmd)

        # Stop the current Maestro Script

    def stopScript(self):
        cmd = chr(0x24)
        self.sendCmd(cmd)

    #############################################################################################


class PCOCameraCompiler(AbstractCompiler):
    TIS_DLL_DIR = "../src/tisgrabber/tisgrabber_x64.dll"
    TIS_Width = ctypes.c_long()
    TIS_Height = ctypes.c_long()
    TIS_BitsPerPixel = ctypes.c_int()
    TIS_colorformat = ctypes.c_int()

    BINFile_Postfix = "PCO_IMG"

    def __init__(self, *args, camera_name=None, save_option='binary', **kwargs):
        super(PCOCameraCompiler, self).__init__(*args, **kwargs)

        self.frame_rate = 1000 / self.refresh_interval
        self._camera_name = camera_name
        self._buffer_name = None
        self._buf_img = None
        self.frame_shape = None
        self._params = {"CameraName": None, 'VideoFormat': None,
                        'StreamToDisk': False, 'SaveDir': None, 'SaveName': None, 'InitTime': None,
                        'FrameCount': 0, 'FrameTime': 0}
        self.streaming = False
        self._BIN_FileHandle = None
        self._stream_init_time = None
        self._n_frame_streamed = None

        if save_option in ['binary', 'movie']:
            self.save_option = save_option
        else:
            raise ValueError("save_option must be either 'binary' or 'movie'")

        for k, v in self._params.items():
            self.create_state(k, v)
        self._init_camera()

    def _init_camera(self):
        self.info("Searching camera...")
        while self._params['CameraName'] is None:
            self._params['CameraName'] = self.get_state('CameraName')
        self.info(f"Camera {self._params['CameraName']} found")
        self.camera = pco.Camera()
        self.camera.record(number_of_images=5,mode='fifo')
        self.camera.wait_for_first_image()
        # self.camera.set_exposure_time(self.refresh_interval)
        self.update_video_format()
        self.watch_state('CameraName', self._params['CameraName'])
        self.info(f"Camera {self._params['CameraName']} initialized")

    def update_video_format(self):
        buffer_name = "frame_PCO_cam"
        self.info('Request ignored because updating video format is not available for PCO camera')
        frame,meta = self.camera.image()
        self.frame_shape = frame.shape
        if self.has_buffer(buffer_name):
            self.set_buffer(buffer_name, frame)
        else:
            self.create_shared_buffer(buffer_name, frame)
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
                self.process_frame()
        except:
            self.error("An error occurred while updating the camera")

    def process_frame(self):
        self._streaming_setup()
        self.camera.wait_for_first_image()
        frame, meta = self.camera.image(0xFFFFFFFF)
        frame_time = time.perf_counter()
        self.set_buffer(self._buffer_name, frame)
        self._data_streaming(frame_time, frame)

    def _data_streaming(self, frame_time, frame):
        if self.streaming:
            frame_time = frame_time - self._stream_init_time
            # Write to AUX file
            n_frame = self._n_frame_streamed

            if self.save_option == 'binary':
                # Write to BIN file
                self._BIN_FileHandle.write(bytearray(frame))
            elif self.save_option == 'movie':
                # Write to movie file
                frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
                self._BIN_FileHandle.write(frame)

            self._n_frame_streamed += 1
            self.set_state('FrameCount', self._n_frame_streamed)

    def _streaming_setup(self):
        if_streaming = self.get_state('StreamToDisk')
        if self.watch_state('StreamToDisk', if_streaming):  # Triggered at the onset and the end of streaming
            if if_streaming:
                self._start_streaming()
            else:  # close all files before streaming stops
                self._stop_streaming()

    def _start_streaming(self):
        save_dir = self.get_state('SaveDir')
        file_name = self.get_state('SaveName')
        init_time = self.get_state('InitTime')
        if save_dir is None or file_name is None or init_time is None:
            self.error("Please set the save directory, file name and initial time before streaming.")
        else:
            if os.path.isdir(save_dir):
                if self.save_option == 'binary':
                    BIN_Fn = f"{self._camera_name}_{file_name}_{self.BINFile_Postfix}.bin"
                    BIN_Fulldir = os.path.join(save_dir, BIN_Fn)
                elif self.save_option == 'movie':
                    BIN_Fn = f"{self._camera_name}_{file_name}_{self.BINFile_Postfix}.avi"
                    BIN_Fulldir = os.path.join(save_dir, BIN_Fn)
                if os.path.isfile(BIN_Fulldir):
                    self.error(f"File {BIN_Fn} already exists in the folder {save_dir}. Please change "
                               f"the save_name.")
                else:
                    if self.save_option == 'binary':
                        self._BIN_FileHandle = open(BIN_Fulldir, 'wb')
                    elif self.save_option == 'movie':
                        self._BIN_FileHandle = cv2.VideoWriter(BIN_Fulldir, cv2.VideoWriter_fourcc(*'MJPG'),
                                                               int(self.frame_rate),
                                                               (self.frame_shape[1], self.frame_shape[0]))

                    self._stream_init_time = init_time
                    self._n_frame_streamed = 0
                    self.streaming = True

    def _stop_streaming(self):
        if self._BIN_FileHandle is not None:
            if self.save_option == 'binary':
                self._BIN_FileHandle.close()
            elif self.save_option == 'movie':
                self._BIN_FileHandle.release()
        self._stream_init_time = None
        self._n_frame_streamed = None
        self.streaming = False

    def disconnect_camera(self):
        self.camera.stop()
        self.camera.close()
        self._params = {"CameraName": None, 'VideoFormat': None,
                        'Trigger': 0, 'FrameCount': 0, 'FrameTime': 0}

    def on_close(self):
        self.camera.stop()
        self.camera.close()
