from bin.app import AbstractGUIAPP
from bin.compiler import QtCompiler
from bin.minion import LoggerMinion

from vispy import scene
from vispy.io import load_data_file, read_png

import PyQt5.QtWidgets as qw
import cv2 as cv



class SimpleGUI(QtCompiler):

    def __init__(self, *args, **kwargs):
        super(SimpleGUI, self).__init__(*args, **kwargs)
        self._videoFn = None
        self._videoHandle = None
        self._image_handle = None
        self._scene_canvas = None
        self._is_playing = False
        self._init_menu()
        self._init_main_window()

    def _setup_scene_canvas(self):

        canvas = scene.SceneCanvas(keys='interactive')
        canvas.size = 800, 600

        # Set up a viewbox to display the image with interactive pan/zoom
        view = canvas.central_widget.add_view()

        # Create the image
        img_data = read_png(load_data_file('mona_lisa/mona_lisa_sm.png'))
        interpolation = 'nearest'

        self._image_handle= scene.visuals.Image(img_data, interpolation=interpolation,
                                    parent=view.scene, method='subdivide')

        # Set 2D camera (the camera will scale to the contents in the scene)
        view.camera = scene.PanZoomCamera(aspect=1)
        # flip y-axis to have correct aligment
        view.camera.flip = (0, 1, 0)
        view.camera.set_range()
        view.camera.zoom(0.1, (250, 200))

        self._scene_canvas = canvas

    def _init_main_window(self):
        self._setup_scene_canvas()
        self.layout_main = qw.QVBoxLayout()
        self.layout_main.addWidget(self._scene_canvas.native)
        self.btn_playVideo = qw.QPushButton('Play')
        self.btn_playVideo.setShortcut('Ctrl+Enter')
        self.btn_playVideo.clicked.connect(self._play_video)

        self.layout_main.addWidget(self.btn_playVideo)
        self.main_widget = qw.QWidget()
        self.main_widget.setLayout(self.layout_main)
        self.setCentralWidget(self.main_widget)

    def _init_menu(self):
        self._menubar = self.menuBar()
        self._menu_file = self._menubar.addMenu('File')

        loadVideo = qw.QAction("Load Video", self)
        loadVideo.setShortcut("Ctrl+O")
        loadVideo.setStatusTip("Load video to play")
        loadVideo.triggered.connect(self.load_video)

        Exit = qw.QAction("Quit", self)
        Exit.setShortcut("Ctrl+Q")
        Exit.setStatusTip("Exit program")
        Exit.triggered.connect(self.close)

        self._menu_file.addAction(loadVideo)
        self._menu_file.addAction(Exit)

    def load_video(self):
        self._videoFn = qw.QFileDialog.getOpenFileName(self, 'Open file', '.', "Video files (*.avi)")[0]
        self._videoHandle = cv.VideoCapture(self._videoFn)
        ret, frame = self._videoHandle.read()
        if ret:
            self._image_handle.set_data(frame)
            self._videoHandle.set(cv.CAP_PROP_POS_FRAMES, 0)
        else:
            self.error('The video could not be loaded.')

    def _play_video(self):
        if self._is_playing:
            self._is_playing = False
            self.btn_playVideo.setText('Play')
        else:
            if self._videoHandle is not None:
                self._is_playing = True
                self.btn_playVideo.setText('Pause')
                self._videoHandle.set(cv.CAP_PROP_POS_FRAMES, 0)
            else:
                self.info('No video loaded.')

    def on_time(self, t):
        if self._videoHandle is not None:
            if self._is_playing:
                ret, frame = self._videoHandle.read()
                if ret:
                    self._image_handle.set_data(frame)
                    self._scene_canvas.update()
                else:
                    self._is_playing = False
                    self.btn_playVideo.setText('Play')
                    self._videoHandle.set(cv.CAP_PROP_POS_FRAMES, 0)


class SimpleApp(AbstractGUIAPP):
    def __init__(self, *args, **kwargs):
        super(SimpleApp, self).__init__(*args, **kwargs)

    def initialize(self):
        super().initialize()
        self._win = SimpleGUI(self)
        self.info("Camera Interface initialized.")
        self._win.show()


if __name__ == '__main__':

    GUI = SimpleApp('GUI', refresh_interval=5)
    logger = LoggerMinion('TestCam logger')
    logger.set_level('DEBUG')

    GUI.attach_logger(logger)

    logger.run()
    GUI.run()
