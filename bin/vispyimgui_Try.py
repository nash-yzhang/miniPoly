from PyQt5.QtWidgets import QApplication, QMainWindow, QPushButton
from PyQt5.QtWidgets import QVBoxLayout, QWidget,QAction,QFileDialog,QMenuBar,QMenu

from vispy import app as vapp
import sys
from sphModel import *
from vispy import app, gloo
from vispy.util.transforms import translate, rotate, perspective

#%%
class VCanvas(app.Canvas):
    _default_VS = """
    #version 130
    attribute vec3 a_pos;
    varying vec3 v_pos;
    uniform mat4 u_view;
    uniform mat4 u_model;
    uniform mat4 u_projection;
    void main () {
        v_pos = a_pos;
        gl_Position = u_projection * u_view * u_model * vec4(a_pos, 1.0);
    }
    """

    _default_FS = """
    uniform float u_time;
    void main() {
        gl_FragColor = vec4(vec3(sin(u_time),cos(u_time),sin(u_time+1.57/2))/2.+.5, 1.);
    }
    """

    def __init__(self,FS = None):
        vapp.Canvas.__init__(self, keys='interactive')
        if not FS:
            self.FS = self._default_FS
        else:
            self.FS = FS
        self.program = gloo.Program(self._default_VS,self.FS)
        V,F = uv_sphere(15,8)
        self.translate = -5
        view = translate((0, 0, self.translate))
        model = np.eye(4, dtype=np.float32)
        self.program['u_model'] = model
        self.program['u_view'] = view
        self.phi, self.theta = 0, 0
        self.program['a_pos'] = qn.qn(V)['xyz'].astype(np.float32)
        self.sph_index = gloo.IndexBuffer(F.astype(np.uint16))
        self.timer = vapp.Timer('auto', self.on_timer, start=True)
        gloo.set_state(clear_color='k', depth_test=True,)
        self.events.mouse_press.connect((self, "on_mouse_motion"))
        self.events.mouse_release.connect((self, "on_mouse_motion"))
        self.events.mouse_move.connect((self, "on_mouse_motion"))

    def on_draw(self,event):
        gloo.clear(depth=True)
        u_time = self.timer.elapsed
        self.program['u_time'] = u_time
        self.program.draw('triangles',self.sph_index)

    def on_resize(self, event):
        self.activate_zoom()

    def activate_zoom(self):
        gloo.set_viewport(0, 0, *self.physical_size)
        projection = perspective(45.0, self.size[0] / float(self.size[1]),
                                 2.0, 10.0)
        self.program['u_projection'] = projection

    def on_timer(self, event):
        self.update()

    def on_mouse_motion(self, event):
        if event.is_dragging and len(event.trail()) > 1:
            delta = event.trail()
            delta = delta[-2, :] - delta[-1, :]
            self.phi += delta[0] / self.size[0] * np.pi * 100
            self.theta -= delta[1] / self.size[1] * np.pi * 50
            self.model = np.dot(rotate(self.phi, (0, -1, 0)),
                                rotate(self.theta, (1, 0, 0)))
            self.program['u_model'] = self.model


    def on_mouse_wheel(self, event):
        self.translate += event.delta[1] / 10
        self.view = translate((0, 0, self.translate))
        self.program['u_view'] = self.view
        self.update()


class vispyCanvas(QWidget):
    """
    This "window" is a QWidget. If it has no parent, it
    will appear as a free-floating window as we want.
    """
    def __init__(self,FS=None):
        super().__init__()
        self._vcanvas = VCanvas(FS)
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
        self.setWindowTitle("Controller")
        self.resize(400,200)
        self._menubar = self.menuBar()
        self._menu_file = self._menubar.addMenu('File')
        loadfile = QAction("Load",self)
        loadfile.setShortcut("Ctrl+O")
        loadfile.setStatusTip("Load fragment shader file")
        loadfile.triggered.connect(self.loadfile)
        self._menu_file.addAction(loadfile)
        self.button = QPushButton("Toggle GL Canvas")
        self.button.clicked.connect(self.show_new_window)
        self.setCentralWidget(self.button)
        self.w = None
        self._fs = None

    def loadfile(self):
        fname = QFileDialog.getOpenFileName(self,'Open File','.',"frag shader (*.glsl)","",QFileDialog.DontUseNativeDialog)
        self._fs = load_shaderfile(fname[0])

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