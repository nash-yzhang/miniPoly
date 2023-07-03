import logging
from logging.handlers import QueueListener
from multiprocessing import Queue

from bin.minion import BaseMinion, TimerMinion, MinionLogHandler, LOG_LVL_LOOKUP_TABLE
import sys
from time import time
from vispy import app
import vispy
import PyQt5.QtWidgets as qw
from qt_material import apply_stylesheet
# from bin.gui import BaseGUI
# from bin.display import GLDisplay

class AbstractAPP(TimerMinion):
    # The same as TimerMinion, just for reference structural clarity
    def __init__(self, name, compiler, refresh_interval=10, **kwargs):
        super(AbstractAPP, self).__init__(name, refresh_interval)
        self._param_to_compiler = kwargs
        self._compiler = compiler

    def initialize(self):
        super().initialize()
        try:
            self._compiler = self._compiler(self, **self._param_to_compiler)
        except Exception as e:
            self.error(f"{self.name} could not be created because of {e}")
            return None
        self.info(f"{self.name} initialized")

class GUIAPP(AbstractAPP):

    def __init__(self, *args, **kwargs):
        super(GUIAPP, self).__init__(*args, **kwargs)
        self._win = None

    def initialize(self):
        super().initialize()
        self._win = self._compiler
        self._win.show()

class StreamingAPP(AbstractAPP):

    def __init__(self, *args, timer_minion=None, trigger_minion=None, **kwargs):
        super(StreamingAPP, self).__init__(*args, **kwargs)

        if timer_minion is None:
            self.error(f"{self.name} could not be created because the '[timer_minion]' is not set")
            return None

        if trigger_minion is None:
            self.error(f"{self.name} could not be created because the '[trigger_minion]' is not set")
            return None

        self._param_to_compiler['timer_minion'] = timer_minion
        self._param_to_compiler['trigger_minion'] = trigger_minion



class AbstractGLAPP(TimerMinion):
    def __init__(self, name, compiler, refresh_interval=10, **kwargs):
        super(AbstractGLAPP, self).__init__(name, refresh_interval)
        self._param_to_compiler = kwargs
        self._compiler = compiler

    def initialize(self):
        self._app = vispy.app.application.Application(backend_name='PyQt5')
        super().initialize()
        self._compiler = self._compiler(self, **self._param_to_compiler)
        self._compiler.initialize()
        self.info(f"OpenGL app '{self.name}' initialized")
        self._compiler.show()

    def on_time(self,t):
        self._app.process_events()


class AbstractGUIAPP(TimerMinion):
    def __init__(self, name, compiler, refresh_interval=10, **kwargs):
        super(AbstractGUIAPP, self).__init__(name, refresh_interval)
        self._param_to_compiler = kwargs
        self._compiler = compiler

    def initialize(self):
        self._app = qw.QApplication(sys.argv)
        apply_stylesheet(self._app, theme='dark_red.xml')
        super().initialize()
        self._compiler = self._compiler(self, **self._param_to_compiler)
        self.info(f"GUI '{self.name}' initialized")
        self._compiler.show()

    def on_time(self,t):
        self._app.processEvents()
        self.poll_GUI_windows()

    def poll_GUI_windows(self):
        win_status = []
        for win in self._app.allWindows():
            win_status.append(win.isVisible())
        if not any(win_status):
            self.shutdown()

    def shutdown(self):
        def kill_minion(minion_name):
            self.set_state_to(minion_name, 'status', -1)

        safe_to_shutdown = False
        while not safe_to_shutdown:
            minion_status = self.poll_minion(kill_minion)
            if not any(minion_status):
                safe_to_shutdown = True

        self.status = -1


class LoggerMinion(BaseMinion, QueueListener):
    DEFAULT_LOGGER_CONFIG = {
        'version': 1,
        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
                'level': 'INFO'
            }
        },
        'root': {
            'handlers': ['console'],
            'level': 'DEBUG'
        }
    }

    DEFAULT_LISTENER_CONFIG = {
        'version': 1,
        'disable_existing_loggers': True,
        'respect_handler_level': True,
        'formatters': {
            'detailed': {
                'class': 'logging.Formatter',
                'format': '%(asctime)-4s  %(name)-8s %(levelname)-8s %(processName)-10s %(message)s'
            },
            'simple': {
                'class': 'logging.Formatter',
                'format': '%(name)-8s %(levelname)-8s %(processName)-10s %(message)s'
            }
        },
        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
                'formatter': 'simple',
                'level': 'INFO'
            },
            'file': {
                'class': 'logging.FileHandler',
                'filename': 'minions.log',
                'mode': 'w',
                'formatter': 'detailed',
                'level': 'DEBUG'
            },
            'errors': {
                'class': 'logging.FileHandler',
                'filename': 'minions-errors.log',
                'mode': 'w',
                'formatter': 'detailed',
                'level': 'INFO'
            }
        },
        'root': {
            'handlers': ['console', 'file', 'errors'],
            'level': 'DEBUG'
        }
    }

    def __init__(self, name, logger_config=None, listener_config=None):
        super(LoggerMinion, self).__init__(name=name)

        if logger_config is None:
            logger_config = self.DEFAULT_LOGGER_CONFIG
        if listener_config is None:
            listener_config = self.DEFAULT_LISTENER_CONFIG

        logging.config.dictConfig(logger_config)
        self.logger = None
        # Start logger after run() as logger object won't pass the pickling process and will be switched off
        self.queue = Queue()
        self.handlers = [MinionLogHandler()]
        self.respect_handler_level = False
        self.listener_config = listener_config
        self.hasConfig = False
        self.reporter = []

    def set_level(self, level):
        level = level.upper()
        if level in LOG_LVL_LOOKUP_TABLE.keys():
            logLevel = LOG_LVL_LOOKUP_TABLE[level]
            logger = logging.getLogger(self.name)
            logger.setLevel(logLevel)
            for handler in logger.handlers:
                handler.setLevel(logLevel)
        else:
            self.warning(f"Unknown logging level: {level}")

    def register_reporter(self, reporter):
        self.connect(reporter)
        self.reporter.append(reporter.name)

    def poll_reporter(self):
        reporter_is_dead = [True] * len(self.reporter)
        for i, m in enumerate(self.reporter):
            err_counter = 0
            while err_counter < 3:
                # Request for 3 times, if all return None (error), then consider alive to receive further error messages
                is_alive = self.is_minion_alive(m)
                if is_alive is True:
                    reporter_is_dead[i] = False
                    break
                elif is_alive is False:
                    reporter_is_dead[i] = True
                    break
                elif is_alive is None:
                    err_counter += 1

        return all(reporter_is_dead)

    def main(self):
        if not self.hasConfig:
            logging.config.dictConfig(self.listener_config)
            self.hasConfig = True

        if self.logger is None:
            # self.logger starts only after the process has started
            self.logger = logging.getLogger(self.name)
            self.logger.setLevel(logging.INFO)
            self.info('----------------- START LOGGING -----------------')

        record = self.dequeue(True)
        self.handle(record)
        if self.poll_reporter():
            self.shutdown()

    def shutdown(self):
        while not self.queue.empty():
            record = self.dequeue(True)
            self.handle(record)
        self.info('----------------- STOP LOGGING -----------------')
        self.set_state_to(self.name, "status", -1)
