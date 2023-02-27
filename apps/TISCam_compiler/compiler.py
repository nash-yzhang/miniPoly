import PyQt5.QtWidgets as qw
import PyQt5.QtGui as qg
import PyQt5.QtCore as qc

from bin.compiler import QtCompiler
from src.tisgrabber import tisgrabber as tis

class CameraGUI(QtCompiler):

    def __init__(self, *args, **kwargs):
        super(CameraGUI, self).__init__(*args, **kwargs)
        self._camera_minions = [i for i in self.get_linked_minion_names() if 'tiscam' in i.lower()]
        self._connected_camera_minions = {}
        self._camera_param = {}
        self._videoStreams = {}

        self.layout_Main = qw.QHBoxLayout()
        self._tiscamHandle = tis.TIS_CAM()

        self._deviceList = self._tiscamHandle.GetDevices()
        self._init_menu()

        self.main_widget = qw.QWidget()
        self.main_widget.setLayout(self.layout_Main)
        self.setCentralWidget(self.main_widget)

    def on_time(self, t):
        for camName, mi in self._connected_camera_minions.items():
            frame = self.get_buffer_from(mi, 'frame')
            if frame is not None:
                self._videoStreams[camName][1].setPixmap(qg.QPixmap.fromImage(qg.QImage(frame, frame.shape[1], frame.shape[0], frame.strides[0],
                                                             qg.QImage.Format_RGB888)))
        self._processHandler.on_time(t)


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
        layout_videoFormat.addWidget(qw.QLabel('Select video format:'))
        layout_videoFormat.addWidget(self.camconfig_videoFormat_list)

        layout_confirm = qw.QHBoxLayout()
        self.camconfig_confirm = qw.QPushButton('Add')
        self.camconfig_confirm.clicked.connect(self.connect_camera)
        self.camconfig_cancel = qw.QPushButton('Cancel')
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
        self.camdisconn_confirm.clicked.connect(self.disconnect_camera)
        self.camdisconn_cancel = qw.QPushButton('Cancel')
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

        self._camera_param[cameraName] = {
            'VideoFormat': self.camconfig_videoFormat_list.currentText(),
            'ExposureTime': None,
            'Gain': None,
            'Trigger':0,
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
                self._connected_camera_minions[cameraName] = mi

            self.setupCameraFrameGUI(cameraName)
        self.camConfigWindow.close()

    def disconnect_camera(self):

        cameraName = self.camconfig_camera_list.currentText()

        self.set_state_to(self._connected_camera_minions[cameraName], 'CameraName', None)
        self.layout_Main.removeWidget(self._videoStreams[cameraName][0])
        self._videoStreams.pop(cameraName)
        self._connected_camera_minions.pop(cameraName)
        self._camera_param.pop(cameraName)
        self.disconnectWindow.close()

    def setupCameraFrameGUI(self, cameraName):
        self._videoStreams[cameraName] = [qw.QWidget(),
                                          qw.QLabel(cameraName)]
                                          # qw.QLabel('Gain: '),
                                          # qw.QSlider(qc.Qt.Horizontal),
                                          # qw.QLineEdit(),
                                          # qw.QLabel('Exposure time: '),
                                          # qw.QSlider(qc.Qt.Horizontal),
                                          # qw.QLineEdit()]
        cameraWidget = self._videoStreams[cameraName][0]
        layout = qw.QVBoxLayout()
        self._videoStreams[cameraName][1].setPixmap(qg.QPixmap())

        # layout_Gain = qw.QHBoxLayout()
        # Gain_label = self._videoStreams[cameraName][1]
        # Gain_slider = self._videoStreams[cameraName][2]
        # Gain_text = self._videoStreams[cameraName][3]
        # Gain_text.setFixedWidth(30)
        # Gain_slider.setMinimum(1)
        # Gain_slider.setMaximum(60)
        # Gain_slider.setValue(30)
        # Gain_slider.setFixedWidth(100)
        # Gain_slider.valueChanged.connect(lambda: self.setGain(cameraName))
        #
        # layout_Gain.addWidget(Gain_label)
        # layout_Gain.addWidget(Gain_text)
        # layout_Gain.addWidget(Gain_slider)
        #
        #
        # layout_ft = qw.QHBoxLayout()
        # ft_label = self._videoStreams[cameraName][4]
        # ft_slider = self._videoStreams[cameraName][5]
        # ft_text = self._videoStreams[cameraName][6]
        # ft_text.setFixedWidth(30)
        # ft_slider.setMinimum(1)
        # ft_slider.setMaximum(250)
        # ft_slider.setValue(30)
        # ft_slider.setFixedWidth(100)
        # ft_slider.valueChanged.connect(lambda: self.setExposureTime(cameraName))
        #
        # layout_ft.addWidget(ft_label)
        # layout_ft.addWidget(ft_text)
        # layout_ft.addWidget(ft_slider)

        layout.addWidget(qw.QLabel(cameraName))
        layout.addWidget(self._videoStreams[cameraName][1])
        cameraWidget.setLayout(layout)
        # layout.addLayout(layout_Gain)
        # layout.addLayout(layout_ft)
        self.layout_Main.addWidget(cameraWidget)

    def setGain(self, cameraName):
        gain = self._videoStreams[cameraName][2].value()
        self._videoStreams[cameraName][3].setText(str(gain))
        minion_name = self._connected_camera_minions[cameraName]
        self.set_state_to(minion_name, 'Gain', gain)

    def setExposureTime(self, cameraName):
        exposureTime = self._videoStreams[cameraName][5].value()
        self._videoStreams[cameraName][6].setText(str(exposureTime))
        minion_name = self._connected_camera_minions[cameraName]
        self.set_state_to(minion_name, 'ExposureTime', exposureTime)