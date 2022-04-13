import multiprocessing as mp
from multiprocessing import Value, Queue, Event
import warnings
from time import time, sleep
import logging
import logging.config
import logging.handlers as lh
from logging.handlers import QueueListener

DEFAULT_LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': True,
    'handlers': {
        'queue': {
            'class': 'logging.handlers.QueueHandler',
        }
    },
    'root': {
        'handlers': ['queue'],
        'level': 'DEBUG'
    }
}


class BaseMinion:
    @staticmethod
    def innerLoop(hook):
        STATE = hook.get_state()
        if hook._log_config is not None:
            logging.config.dictConfig(hook._log_config)
            hook.logger = logging.getLogger(hook.name)
        while STATE >= 0:
            if STATE == 1:
                hook.main()
            elif STATE == 0:
                hook.log(logging.INFO,hook.name + " is suspended\n")
                sleep(0.01)
            STATE = hook.get_state()
        hook._shutdown()

    def __init__(self, name):
        self.name = name
        self.source = {}  # a dictionary of output channels storing rpc function name-value pair (marshalled) E.g.: {'receiver_minion_1':('terminate',True)}
        self.target = {}  # a dictionary of inbox for receiving rpc calls
        self.state = {'{}_{}'.format(self.name, 'status'): Value('i', 0)}
        self.sharedBuffer = {}  # a dictionary of inbox for receiving rpc calls
        self._log_config = None
        self.logger = None

    def add_source(self, src):
        self.share_state_handle(src.name, "status", src.get_state_handle())
        self.source[src.name] = src.target[self.name]

    def del_source(self, src_name):
        for key in list(self.state.keys()):
            if src_name in key:
                self.state.pop(key, 'None')
        self.source[src_name].close()

    def add_target(self, tgt):
        self.share_state_handle(tgt.name, "status", tgt.get_state_handle())
        self.target[tgt.name] = Queue()
        tgt.add_source(self)

    def del_target(self, tgt_name):
        for key in list(self.state.keys()):
            if tgt_name in key:
                self.state.pop(key, 'None')
        self.target[tgt_name].close()

    def send(self, tgt_name, val):
        if self.get_state() > 0:
            chn = self.target[tgt_name]
            if chn is None:
                self.log(logging.ERROR,"Send failed: Queue [{}] does not exist".format(tgt_name))
                return None
            if not chn.full():
                chn.put(val)
            else:
                self.log(logging.WARNING," Send failed: the queue for '{}' is fulled".format(tgt_name))
        else:
            self.log(logging.ERROR,"Send failed: '{}' has been terminated".format(tgt_name))

    def get(self, src_name):
        chn = self.source[src_name]
        if chn is None:
            self.log(logging.ERROR,"Receive failed: Queue [{}] does not exist".format(src_name))
            return None
        if self.get_state() > 0:
            if not chn.empty():
                received = chn.get()
            else:
                self.log(logging.WARNING,"Empty Queue")
                received = None
        else:
            self.log(logging.ERROR,"Receive failed: '{}' has been terminated".format(src_name))
            received = None
        return received

    def add_buffer(self, buffer_name, buffer_handle):
        self.sharedBuffer[buffer_name] = buffer_handle

    def get_state(self, minion_name=None, category="status"):
        if minion_name is None:
            minion_name = self.name
        return self.state['{}_{}'.format(minion_name, category)].value

    def get_state_handle(self, minion_name=None, category="status"):
        if minion_name is None:
            minion_name = self.name
        return self.state['{}_{}'.format(minion_name, category)]

    def set_state(self, minion_name, category, value):
        self.state['{}_{}'.format(minion_name, category)].value = value

    def share_state_handle(self, minion_name, category, value):
        self.state.update({'{}_{}'.format(minion_name, category): value})

    def attach_logger(self, logger):
        config_worker = {
            'version': 1,
            'disable_existing_loggers': True,
            'handlers': {
                'queue': {
                    'class': 'logging.handlers.QueueHandler',
                    'queue': logger.queue
                }
            },
            'root': {
                'handlers': ['queue'],
                'level': 'DEBUG'
            }
        }
        self._log_config = config_worker
        self._log_queue = logger.queue
        logger.register_reporter(self)

    def log(self,*args):
        if self.logger is not None:
            self.logger.log(*args)
        else:
           warnings.warn("[{}]-[Warning] Logger unattached".format(self.name))

    def run(self):
        self.Process = mp.Process(target=BaseMinion.innerLoop, args=(self,))
        self.set_state(self.name, "status", 1)
        self.Process.start()

    def main(self):
        pass

    def shutdown(self):
        self.log(logging.INFO, self.name + " is off")
        self.set_state(self.name, "status", -1)

    def _shutdown(self):
        for i in self.source.keys():
            self.del_source(i)
        for i in self.target.keys():
            self.del_target(i)
        if self.Process._popen:
            self.Process.join()

# class MinionLogListener(QueueListener):
#     """
#     A simple handler for logging events. It runs in the listener process and
#     dispatches events to loggers based on the name in the received record,
#     which then get dispatched, by the logging system, to the handlers
#     configured for those loggers.
#     """
#
#     def _monitor(self):
#         q = self.queue
#         has_task_done = hasattr(q, 'task_done')
#         while True:
#             try:
#                 record = self.dequeue(True)
#                 if record is self._sentinel:
#                     if has_task_done:
#                         q.task_done()
#                     break
#                 self.handle(record)
#                 if has_task_done:
#                     q.task_done()
#             except self.queue:
#                 break

class MinionLogHandler:
    """
    A simple handler for logging events. It runs in the listener process and
    dispatches events to loggers based on the name in the received record,
    which then get dispatched, by the logging system, to the handlers
    configured for those loggers.
    """

    def handle(self, record):
        if record.name == "root":
            logger = logging.getLogger()
        else:
            logger = logging.getLogger(record.name)
        if logger.isEnabledFor(record.levelno):
            # The process name is transformed just to show that it's the listener
            # doing the logging to files and console
            record.processName = '%s (for %s)' % (mp.current_process().name, record.processName)
            logger.handle(record)

class LoggerMinion(BaseMinion):
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
                'formatter': 'detailed'
            },
            'errors': {
                'class': 'logging.FileHandler',
                'filename': 'minions-errors.log',
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

    def __init__(self, logger_config=DEFAULT_LOGGER_CONFIG, listener_config=DEFAULT_LISTENER_CONFIG):
        self.name = 'logger'
        super(LoggerMinion, self).__init__(name=self.name)
        logging.config.dictConfig(logger_config)
        self.logger = logging.getLogger("SETUP")
        self.queue = Queue()
        self.handlers = [MinionLogHandler()]
        self.respect_handler_level = False
        self.listener_config = listener_config
        self.hasConfig = False
        self.reporter = []

    def register_reporter(self,reporter):
        self.share_state_handle(reporter.name, "status", reporter.get_state_handle())
        self.reporter.append(reporter.name)

    def poll_reporter(self):
        return any([self.get_state(i)==1 for i in self.reporter])

    def prepare(self, record):
        """
        Prepare a record for handling.

        This method just returns the passed-in record. You may want to
        override this method if you need to do any custom marshalling or
        manipulation of the record before passing it to the handlers.
        """
        return record

    def dequeue(self, block):
        """
        Dequeue a record and return it, optionally blocking.

        The base implementation uses get. You may want to override this method
        if you want to use timeouts or work with custom queue implementations.
        """
        return self.queue.get(block)

    def handle(self, record):
        """
        Handle a record.

        This just loops through the handlers offering them the record
        to handle.
        """
        record = self.prepare(record)
        for handler in self.handlers:
            if not self.respect_handler_level:
                process = True
            else:
                process = record.levelno >= handler.level
            if process:
                handler.handle(record)

    def main(self):
        if not self.hasConfig:
            logging.config.dictConfig(self.listener_config)
            self.hasConfig = True
        record = self.dequeue(True)
        self.handle(record)
        if not self.poll_reporter():
            self.shutdown()

class LoggerMinion_arc:
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
                'formatter': 'detailed'
            },
            'errors': {
                'class': 'logging.FileHandler',
                'filename': 'minions-errors.log',
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

    @staticmethod
    def listener_process(hook, config):
        """
        This could be done in the main process, but is just done in a separate
        process for illustrative purposes.

        This initialises logging according to the specified configuration,
        starts the listener and waits for the main process to signal completion
        via the event. The listener is then stopped, and the process exits.
        """
        logging.config.dictConfig(config)
        listener = logging.handlers.QueueListener(hook.queue, MinionLogHandler())
        listener.start()
        hook.stop_event.wait()
        listener.stop()

    def __init__(self, logger_config=DEFAULT_LOGGER_CONFIG, listener_config=DEFAULT_LISTENER_CONFIG):
        logging.config.dictConfig(logger_config)
        self.logger = logging.getLogger("SETUP")
        self.name = 'logger'
        self.queue = Queue()
        self.stop_event = Event()
        self.Process = mp.Process(target=LoggerMinion.listener_process, args=(self, listener_config))

    def run(self):
        self.Process.start()
        self.logger.info('Started Logger')
