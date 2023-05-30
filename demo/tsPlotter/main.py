# A demo for how to chreate a plotter for time series data with minipoly froamwork.
import numpy as np
import PyQt5.QtWidgets as qw
import PyQt5.QtGui as qg
import PyQt5.QtCore as qc
import pyqtgraph as pg
import time, os
import pyfirmata as pf

from bin.api import StandardGUIAPP, StandardGUICompiler, Logger

class ArduinoHandler()

class TimeSeriesPlotter(StandardGUICompiler):

    def __init__(self, *args):
        super(TimeSeriesPlotter, self).__init__(*args)
        self.time_array = np.zeros(2000,dtype=np.float32)
        self.value_array = np.ones(2000,dtype=np.float32)
        self._tsplots = self.widget_tsplot.plot(self.time_array, self.value_array,pen=pg.mkPen('k', width=2))
        self._registered_pins = {}
    def init_ui(self):
        self.layout_main = qw.QVBoxLayout()

        self.layout_ts_canvas = qw.QHBoxLayout()
        self.layout_ts_canvas.heightForWidth(50)

        self.widget_tsplot = pg.PlotWidget()
        self.widget_tsplot.setBackground('w')

        self._setup_pin_registration_ui()
        self.layout_ts_canvas.addWidget(self.widget_tsplot)
        self.layout_main.addLayout(self.layout_ts_canvas)

        self.main_widget = qw.QWidget()
        self.main_widget.setLayout(self.layout_main)
        self.setCentralWidget(self.main_widget)

    def _setup_pin_registration_ui(self):
        self.layout_registration_combo = qw.QVBoxLayout()
        self.layout_registration_form= qw.QHBoxLayout()

        # Dropdown List - Type
        type_label = qw.QLabel("Type:")
        self.type_combo = qw.QComboBox()
        self.type_combo.addItems(["analog", "digital"])

        # Input Text Field - Number
        number_label = qw.QLabel("Number:")
        self.number_input = qw.QLineEdit()
        onlyInt = qg.QIntValidator()
        onlyInt.setRange(0, 13)
        self.number_input.setValidator(onlyInt)  # Custom validator to accept only integers from 0-13

        # Dropdown List - Mode
        mode_label = qw.QLabel("Mode:")
        self.mode_combo = qw.QComboBox()
        self.mode_combo.addItems(["input", "output", "servo", "pwm"])

        # Register Button
        register_button = qw.QPushButton("Register")
        register_button.clicked.connect(self.register_pin)

        self.layout_registration_form.addWidget(type_label)
        self.layout_registration_form.addWidget(self.type_combo)
        self.layout_registration_form.addWidget(number_label)
        self.layout_registration_form.addWidget(self.number_input)
        self.layout_registration_form.addWidget(mode_label)
        self.layout_registration_form.addWidget(self.mode_combo)
        self.layout_registration_form.addWidget(register_button)

        self.widget_registration_table = qw.QTableWidget()
        self.widget_registration_table.setColumnCount(4)
        self.widget_registration_table.setHorizontalHeaderLabels(["Legend","Pin Class", "Number", "Mode"])
        self.widget_registration_table.setContextMenuPolicy(qc.Qt.CustomContextMenu)
        self.widget_registration_table.customContextMenuRequested.connect(self.show_context_menu)

        self.layout_registration_combo.addLayout(self.layout_registration_form)
        self.layout_registration_combo.addWidget(self.widget_registration_table)

        self.layout_ts_canvas.addLayout(self.layout_registration_combo)

    def register_pin(self):
        pin_color = qg.QColor(*np.random.randint(0, 255, size=3))
        pin_class = self.type_combo.currentText()
        pin_number = self.number_input.text()
        pin_mode = self.mode_combo.currentText()

        row_count = self.widget_registration_table.rowCount()
        self.widget_registration_table.insertRow(row_count)

        item_pin_color = qw.QTableWidgetItem()
        item_pin_color.setBackground(qg.QBrush(pin_color))
        self.widget_registration_table.setItem(row_count, 0, item_pin_color)
        self.widget_registration_table.setItem(row_count, 1, qw.QTableWidgetItem(pin_class))
        self.widget_registration_table.setItem(row_count, 2, qw.QTableWidgetItem(pin_number))
        self.widget_registration_table.setItem(row_count, 3, qw.QTableWidgetItem(pin_mode))

    def show_context_menu(self, pos):
        context_menu = qw.QMenu(self)
        unregister_action = qw.QAction("Unregister", self)
        unregister_action.triggered.connect(self.unregister_row)
        context_menu.addAction(unregister_action)
        context_menu.exec_(self.widget_registration_table.viewport().mapToGlobal(pos))

    def unregister_row(self):
        row = self.widget_registration_table.currentRow()
        self.widget_registration_table.removeRow(row)

    def on_time(self, t):
        self.time_array[:-1] = self.time_array[1:]
        self.time_array[-1] = t
        self.value_array[:-1] = self.value_array[1:]
        self.value_array[-1] = np.sin(t)
        self._tsplots.setData(self.time_array, self.value_array)



if __name__ == '__main__':
    GUI = StandardGUIAPP('GUI', compiler=TimeSeriesPlotter)
    logger = Logger('TestCam logger')
    logger.set_level('DEBUG')

    GUI.attach_logger(logger)
    logger.run()
    GUI.run()
