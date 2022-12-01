import logging

import PyQt5.Qt
import traceback, sys
from vispy import gloo
import os
import numpy as np
from bin.glsl_preset import Renderer
import PyQt5.QtWidgets as qw
import PyQt5.QtCore as qc
from PyQt5.Qt import Qt as qt
from utils import load_shaderfile
import pyfirmata as fmt

from multiprocessing import Value, Queue


class Widget(qw.QWidget):
    def __init__(self, mainW, arduino_port="COM4"):
        super().__init__()
        self._mainWindow = mainW
        self._processHandler = mainW._processHandler
        self._arduino_port = arduino_port
        self.init_arduino()
        self.init_gui()

    def init_arduino(self):
        try:
            self._arduino_board = fmt.Arduino(self._arduino_port)
            self._arduino_iterator = fmt.util.Iterator(self._arduino_board)
            self._arduino_iterator.start()
            self._servo_pin_number = 9
            self._servo_pin = self._arduino_board.get_pin('d:{}:s'.format(self._servo_pin_number))
        except Exception as e:
            self._processHandler.error(traceback.format_exc())

    def init_gui(self):
        self._layout = qw.QVBoxLayout()
        self.setLayout(self._layout)
        self.load_button = qw.QPushButton("Load Shader")
        self.load_button.setShortcut("Ctrl+Shift+O")
        self.load_button.clicked.connect(self.loadfile)
        self.layout().addWidget(self.load_button, 1)
        self._autoR_box = qw.QCheckBox("auto refresh")
        self._autoR_box.setChecked(False)
        self._autoR_box.clicked.connect(self.auto_refresh)
        self.refresh_button = qw.QPushButton("Refresh")
        self.refresh_button.setShortcut("Ctrl+Shift+R")
        self.refresh_button.clicked.connect(self.refresh)
        self._sublayout = qw.QHBoxLayout()
        self._sublayout.addWidget(self._autoR_box)
        self._sublayout.addWidget(self.refresh_button, 1)
        self.layout().addLayout(self._sublayout)
        self._servo_ori_slider = qw.QSlider(qt.Horizontal)
        self._servo_ori_slider.setMinimum(0)
        self._servo_ori_slider.setMaximum(180)
        self._servo_ori_slider.valueChanged.connect(self.change_servo_ori)
        self.layout().addWidget(self._servo_ori_slider)

        spacer = qw.QSpacerItem(1, 1, qw.QSizePolicy.Minimum, qw.QSizePolicy.MinimumExpanding)
        self.layout().addItem(spacer)

        self._fs = None
        os.environ["QT_FILESYSTEMMODEL_WATCH_FILES"] = '1'
        self.FSname = None
        self.FSwatcher = qc.QFileSystemWatcher([])
        self.FSwatcher.fileChanged.connect(self.refresh)

        self._processHandler.create_state('u_barpos', 0.)

    def loadfile(self):
        if self.FSname is not None:
            self.FSwatcher.removePath(self.FSname)
        self._autoR_box.setChecked(False)
        self.FSname = qw.QFileDialog.getOpenFileName(self, 'Open File', './shader',
                                                     "frag shader (*.frag)", ""
                                                     , qw.QFileDialog.DontUseNativeDialog)
        self.FSname = self.FSname[0]
        if self.FSname:
            self._fs = load_shaderfile(self.FSname)
            # self._mainWindow._renderer.reload(self._fs)
            self.rpc_reload()

    def rpc_reload(self):
        self._processHandler.send(self._mainWindow._displayProcName,
                                  ('rendering_shader', self._fs))

    def auto_refresh(self, checked):
        if checked and self.FSname is not None:
            self.FSwatcher.addPath(self.FSname)
        elif not checked and self.FSname is not None:
            self.FSwatcher.removePath(self.FSname)
        else:
            self._autoR_box.setChecked(False)

    def refresh(self, checked):
        if self.FSname is not None:
            self._fs = load_shaderfile(self.FSname)
            # self._mainWindow._renderer.reload(self._fs)
            self.rpc_reload()

    def change_servo_ori(self, val):
        # try:
        # self._servo_pin.write(val)
        # except Exception as e:
        #     self._processHandler.error(traceback.format_exc())

        self._processHandler.set_state_to(self._processHandler.name, 'u_barpos', (val / 90) - 1)
        # self._processHandler.send(self._mainWindow._displayProcName,'uniform',{'u_barpos':(val/90)-1})

    def close(self):
        self._arduino_board.exit()


class Renderer(Renderer):
    def __init__(self, canvas):
        super().__init__(canvas)
        self.VS = """
            #version 130
            attribute vec2 a_pos;
            varying vec2 v_pos;
            void main () {
                v_pos = a_pos;
                gl_PointSize = 10.;
                gl_Position = vec4(a_pos, 0.0, 1.0);
            }
            """

        self.FS = """
            varying vec2 v_pos;
            uniform float u_alpha;
            uniform float u_time;
            uniform float u_barpos;
            void main() {
                float marker = step(.5,distance(gl_PointCoord,vec2(.5)));
                float color = sin(v_pos.x*20.+u_time*30.)/2.-.15+marker;
                float mask  = step(.1,abs(v_pos.x-u_barpos));
                gl_FragColor = vec4(vec3(mask), u_alpha);
            }
        """
        self.program = gloo.Program(self.VS, self.FS)

    def init_renderer(self):
        self.program['a_pos'] = np.array([[-1., -1.], [-1., 1.], [1., -1.], [1., 1.]], np.float32)  # /2.
        self.program['u_time'] = 0
        self.program['u_alpha'] = np.float32(1)

        self.program['u_barpos'] = self.canvas._processHandler.get_state_from(self.canvas._controllerProcName,
                                                                              'u_barpos')
        self.canvas.logger.setlevel(logging.DEBUG)
        gloo.set_state("translucent")
        self.program['u_resolution'] = (self.canvas.size[0], self.canvas.size[1])

    def on_draw(self, event):
        gloo.clear('white')
        u_time = self.canvas.timer.elapsed
        self.program['u_time'] = u_time
        self.program['u_barpos'] = self.canvas._processHandler.get_state_from(self.canvas._controllerProcName,
                                                                              'u_barpos')
        self.program.draw('triangle_strip')
