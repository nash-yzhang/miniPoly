import logging
from datetime import datetime
from logging.handlers import QueueListener
from multiprocessing import Queue

from miniPoly.core.minion import BaseMinion, MinionLogHandler, LOG_LVL_LOOKUP_TABLE


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
                'filename': f'{datetime.now().strftime("%Y%m%d_%H%M%S")}.log',
                'mode': 'w',
                'formatter': 'detailed',
                'level': 'DEBUG'
            },
            'errors': {
                'class': 'logging.FileHandler',
                'filename': f'ERROR_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log',
                'mode': 'w',
                'formatter': 'detailed',
                'level': 'ERROR'
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
        # Start logger after run() as logger object won't pass the pickling core and will be switched off
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
            # self.logger starts only after the core has started
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
