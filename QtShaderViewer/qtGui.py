from PyQt5.QtCore import QFileSystemWatcher
from PyQt5.QtWidgets import QApplication, QMainWindow, QPushButton, QCheckBox
from PyQt5.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget,QAction,QFileDialog,QMenuBar,QMenu
import glsl_preset as gp
import sys
from vispy import app, gloo
from utils import load_shaderfile

#%%
class vispyCanvas(QWidget):
    """
    This "window" is a QWidget. If it has no parent, it
    will appear as a free-floating window as we want.
    """
    def __init__(self,FS=None):
        super().__init__()
        self._vcanvas = gp.sphereCanvas(FS)
        self.setLayout(QVBoxLayout())
        self.layout().addWidget(self._vcanvas.native)
        self.setStyleSheet("background: transparent; border: transparent;")

    def closeEvent(self,event):
        self._vcanvas.timer.stop()
        self._vcanvas.close()
        event.accept()

class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("GLSL viewer")
        self.resize(400,600)
        self._menubar = self.menuBar()
        self._menu_file = self._menubar.addMenu('File')
        loadfile = QAction("Load",self)
        loadfile.setShortcut("Ctrl+O")
        loadfile.setStatusTip("Load fragment shader file")
        loadfile.triggered.connect(self.loadfile)
        self._menu_file.addAction(loadfile)
        self.central_widget = QWidget()               # define central widget
        self.setCentralWidget(self.central_widget)
        self.boxlayout = QVBoxLayout()
        self._vcanvas = gp.glCanvas()
        self._renderer = gp.sphereRenderer(self._vcanvas)
        self._vcanvas.load(self._renderer)
        self.central_widget.setLayout(self.boxlayout)
        self._autoR_box = QCheckBox("auto refresh")
        self._autoR_box.setChecked(False)
        self._autoR_box.clicked.connect(self.auto_refresh)
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setShortcut("Ctrl+R")
        self.refresh_button.clicked.connect(self.refresh)
        self._sphere_box = QCheckBox("Sphere")
        self._sphere_box.setChecked(True)
        self._sphere_box.clicked.connect(self._use_sphere)
        self._plane_box = QCheckBox("Plane")
        self._plane_box.clicked.connect(self._use_plane)
        self.boxlayout.addWidget(self._vcanvas.native)
        self.sublayout = QHBoxLayout()
        self.sublayout.addWidget(self._autoR_box)
        self.sublayout.addWidget(self.refresh_button)
        self.sublayout.addWidget(self._sphere_box)
        self.sublayout.addWidget(self._plane_box)
        self.boxlayout.addLayout(self.sublayout)

        self._fs = None
        self.FSname = None
        self.FSwatcher = QFileSystemWatcher([])

    def loadfile(self):
        self.FSname = QFileDialog.getOpenFileName(self,'Open File','./shader',"frag shader (*.glsl *.vert *.frag)","",QFileDialog.DontUseNativeDialog)
        self.FSname = self.FSname[0]
        if self.FSname:
            self._fs = load_shaderfile(self.FSname)
            self._renderer.reload(self._fs)

    #TODO: implement the auto file update system
    def auto_refresh(self, checked):
        if checked and self._fs is not None:
            self.FSwatcher.addPath(self._fs)
            self.FSwatcher.fileChanged.connect(self.refresh)
        elif not checked and self._fs is not None:
            self.FSwatcher.removePath(self._fs)

    def refresh(self, checked):
        if self._fs is not None:
            self._fs = load_shaderfile(self.FSname)
            self._renderer.reload(self._fs)

    def _use_sphere(self,checked):
        self._renderer = gp.sphereRenderer(self._vcanvas)
        self._vcanvas.load(self._renderer)
        self._sphere_box.setChecked(True)
        self._plane_box.setChecked(False)

    def _use_plane(self,checked):
        self._renderer = gp.planeRenderer(self._vcanvas)
        self._vcanvas.load(self._renderer)
        self._sphere_box.setChecked(False)
        self._plane_box.setChecked(True)

    def show_new_window(self, checked):
        if self.w is None:
            self.w = vispyCanvas(self._fs)
            self.w.show()
        else:
            if not self.w.isVisible():
                self.w = None
                self.w = vispyCanvas()
                self.w.show()
            else:
                self.w.close()
                self.w = None


app = QApplication(sys.argv)
w = MainWindow()
w.show()
app.exec()