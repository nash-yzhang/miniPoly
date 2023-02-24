import os
from time import sleep, time, perf_counter

import multiprocessing as mp
from multiprocessing import Queue, Lock

import logging
import logging.config
from logging import DEBUG, INFO, WARNING, ERROR, CRITICAL
from logging.handlers import QueueListener

from typing import Callable

from bin.buffer import *

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

LOG_LVL_LOOKUP_TABLE = {
    "DEBUG": DEBUG,
    "INFO": INFO,
    "WARNING": WARNING,
    "ERROR": ERROR,
    "CRITICAL": CRITICAL,
}

COMM_WAITING_TIME = 1e-3

SHAREDLOCK = Lock()

class BaseMinion:
    @staticmethod
    def innerLoop(hook: 'BaseMinion'):
        '''
        A dirty way to put BaseMinion as a listener when suspended
        :param hook: Insert self as a hook for using self logger, main process and shutdown method
        '''
        hook._pid = os.getpid()
        hook.prepare_shared_buffer()
        hook.build_init_conn()
        STATE = hook.status
        if hook._log_config is not None:
            logging.config.dictConfig(hook._log_config)
            hook.logger = logging.getLogger(hook.name)
        hook.init_process()
        hook._has_init = False
        while STATE >= 0:
            if STATE == 1:
                if hook._is_suspended:
                    hook._is_suspended = False
                if not hook._has_init:
                    hook.initialize()
                    hook._has_init = True
                hook.main()
            elif STATE == 0:
                if not hook._is_suspended:
                    hook.info(hook.name + " is suspended\n")
                    hook._is_suspended = True
                    hook._has_init = False
                sleep(.1)
            try:
                STATE = hook.status
            except:
                pass
                # print(f'{hook.name}: {traceback.format_exc()}')
        hook._shutdown()

    _INDEX_SHARED_BUFFER_SIZE = 2 ** 16  # The size allocated for storing small shared values/array, each write takes <2 ms

    def __init__(self, name):

        self.logger = None
        self._log_config = None
        self.Process = None
        self._shared_dict = None
        self._is_suspended = False
        self._pid = None

        self.name = name
        self.lock = SHAREDLOCK
        self._queue = {}  # a dictionary of in/output channels storing rpc function name-value pair (marshalled) E.g.: {'receiver_minion_1':('terminate',True)}
        self._watching_state = {}
        self._elapsed = time()

        # The _shared_buffer is a dictionary that contains the shared buffer which will be dynamically created and
        # destroyed. The indices of all shared memories stored in this dictionary will be saved in a dictionary
        # called _shared_buffer_index_dict, whose content will be updated into the _shared_buffer.
        self._shared_buffer = {}
        self._linked_minion = {}
        self.minion_to_link = []

    ############# Logging module #############
    def attach_logger(self, logger: 'LoggerMinion'):
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

    def log(self, *args):
        if self.logger is not None:
            self.logger.log(*args)
        else:
            warnings.warn("[{}]-[Warning] Logger unattached".format(self.name))

    def debug(self, msg):
        self.log(logging.DEBUG, msg)

    def info(self, msg):
        self.log(logging.INFO, msg)

    def warning(self, msg):
        self.log(logging.WARNING, msg)

    def error(self, msg):
        self.log(logging.ERROR, msg)

    ############# shared buffer/state module #############
    def pid_check(self):
        if self._pid is not None:
            current_pid = os.getpid()
            is_pid_changed = current_pid == self._pid
            return current_pid, is_pid_changed
        else:
            return None, None

    def prepare_shared_buffer(self):
        self._shared_dict = SharedDict(f'{self.name}_shared_dict', lock=self.lock, create=True, name=self.name,
                                       size=self._INDEX_SHARED_BUFFER_SIZE)
        self._shared_dict['name'] = self.name
        self._shared_dict['status'] = 1

    def build_init_conn(self, timeout=1000):
        linked_minion = [0] * len(self.minion_to_link)
        t0 = time()
        while (time() - t0) * 1000 < timeout:
            for i, m in enumerate(self.minion_to_link):
                linked_minion[i] = self.link_minion(m)
            if all(i == 1 for i in linked_minion):
                break
            else:
                sleep(0.1)

    def create_shared_buffer(self, name, data, size):
        # The reference name of any shared buffer should have the structure 'b*{minion_name}_{buffer_name}' The
        # builtin state dictionary for all minions are the SharedDict whose name is 'b*{self.name}_shared_dict'
        # The names of all other buffers created later will be saved in the builtin SharedDict as a shared state as
        # name-value pairs: {shared_buffer_reference_name}: {shared_buffer_name};
        # #
        # For safety consideration, it is compulsory to use "with" statement to access any foreign buffers.

        pid, pid_checked = self.pid_check()
        if pid_checked:
            shared_buffer_name = f"{self.name}_{name}"
            shared_buffer_reference_name = f"b*{shared_buffer_name}"
            if shared_buffer_reference_name not in self._shared_dict.keys():
                try:
                    self._shared_buffer[shared_buffer_name] = SharedBuffer(shared_buffer_name, data, size,
                                                                           create=True)  # The list '_shared_buffer" host all local buffer for other minion to access, it also serves as a handle hub for later closing these buffers
                except Exception:
                    self.log(logging.ERROR,
                             f"Error in creating buffer '{shared_buffer_name}'.\n{traceback.format_exc()}")
                self._shared_dict[shared_buffer_reference_name] = shared_buffer_name
            else:
                self.log(logging.ERROR, f"SharedBuffer '{shared_buffer_name}' already exist")
        else:
            self.log(logging.DEBUG, f'Access denied because of the changed PID ({self._pid}->{pid})')

    def link_minion(self, minion_name):
        pid, pid_checked = self.pid_check()
        if pid_checked:
            shared_buffer_name = f"{minion_name}_shared_dict"
            shared_buffer_reference_name = f"b*{shared_buffer_name}"
            if shared_buffer_reference_name not in self._shared_dict.keys():
                try:
                    with SharedDict(shared_buffer_name, lock=self.lock) as tmp_dict:
                        # Just to test if the SharedDict exist and the name is correct
                        dict_name = tmp_dict.get('name')
                        if dict_name is None:
                            dict_name = 'N/A'
                        if dict_name == minion_name:
                            self.log(logging.INFO, f"Successfully connected to '{minion_name}.")
                            self._shared_dict[shared_buffer_reference_name] = shared_buffer_name
                            self._linked_minion[minion_name] = [
                                'shared_dict']  # The name of the shared buffer from this minion
                            return 1
                        else:
                            self.log(logging.ERROR,
                                     f'[{self.name}] Pre-execution error: The "name" state of the linked shared buffer {dict_name} is inconsistent with input minion name {minion_name}.')
                            return 2
                except FileNotFoundError:
                    self.log(logging.INFO, f"SharedDict '{minion_name} not found'.")
                    return -1
                except:
                    self.log(logging.ERROR, f"Error when connecting to '{minion_name}'.\n{traceback.format_exc()}")
                    return 3
            else:
                self.log(logging.INFO, f"Already linked to minion: {minion_name}")
                return 1
        else:
            self.log(logging.DEBUG, f'Access denied because of the changed PID ({self._pid}->{pid})')

    def link_foreign_buffer(self, minion_name: str, buffer_name: str):
        """
        Connect to shared buffer created by other minions

        :param minion_name: Foreign minion's name
        :param buffer_name: Foreign minion's buffer's name
        """
        pid, pid_checked = self.pid_check()
        if pid_checked:
            shared_buffer_reference_name = f"b*{minion_name}_{buffer_name}"
            if shared_buffer_reference_name not in self._shared_dict.keys():
                if minion_name in self._linked_minion.keys():
                    with SharedDict(f"{minion_name}_shared_dict", lock=self.lock, create=False) as tmp_dict:
                        if shared_buffer_reference_name in tmp_dict.keys():
                            self._shared_dict[shared_buffer_reference_name] = tmp_dict[shared_buffer_reference_name]
                        else:
                            self.log(logging.ERROR, f"Unknown foreign buffer '{buffer_name}' in minion '{minion_name}'")
                    self._linked_minion[minion_name].append(
                        buffer_name)  # The name of the shared buffer from this minion
                else:
                    self.log(logging.ERROR, f"Unknown minion: '{minion_name}'")

            else:
                self.log(logging.INFO, f"Already linked to the foreign buffer {buffer_name} from minion {minion_name}")
        else:
            self.log(logging.DEBUG, f'Access denied because of the changed PID ({self._pid}->{pid})')

    def create_state(self, state_name: str, state_val: object):
        pid, pid_checked = self.pid_check()
        if pid_checked:
            if state_name in self._shared_dict.keys():
                self.log(logging.ERROR, f"State '{state_name}' already exists")
            else:
                self._shared_dict[state_name] = state_val
                self.log(logging.INFO, f"Shared state: '{state_name}' created")
        else:
            self.log(logging.DEBUG, f'Access denied because of the changed PID ({self._pid}->{pid})')

    def remove_state(self,state_name: str):
        pid, pid_checked = self.pid_check()
        if pid_checked:
            if state_name in self._shared_dict.keys():
                del self._shared_dict[state_name]
                self.log(logging.INFO, f"Shared state: '{state_name}' DELETED")
            else:
                self.log(logging.ERROR, f"State '{state_name}' cannot be deleted because it does not exist")

        else:
            self.log(logging.DEBUG, f'Access denied because of the changed PID ({self._pid}->{pid})')

    def get_shared_state_names(self,minion_name:str):
        pid, pid_checked = self.pid_check()
        if pid_checked:
            if minion_name == self.name:
                    return list(self._shared_dict.keys())

            elif minion_name in self._linked_minion.keys():
                if self.is_minion_alive(minion_name):
                    with SharedDict(f"{minion_name}_shared_dict", lock=self.lock, create=False) as tmp_dict:
                        return list(tmp_dict.keys())
                else:
                    self.log(logging.DEBUG, f"Dead minion '{minion_name}' or errors in connecting to its shared buffer")
            else:
                self.log(logging.DEBUG, f"Unknown minion: '{minion_name}'")
        else:
            self.log(logging.DEBUG, f'Access denied because of the invalid PID ({self._pid}->{pid})')


    def get_state_from(self, minion_name: str, state_name: str):
        """
        Get the value stored in the shared dictionary of self or foreign minions by dict key
        :param minion_name: str, minion's name
        :param state_name: str, shared dictionary key
        :return:
            obj: None if any error occurs in the process
        """
        state_val = None  # Return None if exception to avoid error
        pid, pid_checked = self.pid_check()
        if pid_checked:
            if minion_name == self.name:
                if state_name in self._shared_dict.keys():
                    state_val = self._shared_dict.get(state_name)
                else:
                    self.log(logging.DEBUG, f"Unknown state: '{state_name}'")

            elif minion_name in self._linked_minion.keys():
                if self.is_minion_alive(minion_name):
                    with SharedDict(f"{minion_name}_shared_dict", lock=self.lock, create=False) as tmp_dict:
                        if state_name in tmp_dict.keys():
                            state_val = tmp_dict[state_name]
                        else:
                            self.log(logging.DEBUG, f"Unknown foreign state '{state_name}' in minion '{minion_name}'")
                else:
                    self.log(logging.DEBUG, f"Dead minion '{minion_name}' or errors in connecting to its shared buffer")
            else:
                self.log(logging.DEBUG, f"Unknown minion: '{minion_name}'")
        else:
            self.log(logging.DEBUG, f'Access denied because of the invalid PID ({self._pid}->{pid})')

        return state_val

    def get_state(self, state_name: str):
        return self.get_state_from(self.name, state_name)

    def set_state_to(self, minion_name: str, state_name: str, val):
        """
        Set the value stored in the shared dictionary of self or foreign minions by dict key
        :param minion_name: str, minion's name
        :param state_name: str, shared dictionary key
        :param val: the value to be set
        """
        pid, pid_checked = self.pid_check()
        if pid_checked:
            if minion_name == self.name:
                if state_name in self._shared_dict.keys():
                    self._shared_dict[state_name] = val
                else:
                    self.log(logging.ERROR, f"Unknown state: '{state_name}'")

            elif minion_name in self._linked_minion.keys():
                if self.is_minion_alive(minion_name):
                    with SharedDict(f"{minion_name}_shared_dict", lock=self.lock, create=False) as tmp_dict:
                        if state_name in tmp_dict.keys():
                            tmp_dict[state_name] = val
                        else:
                            self.log(logging.ERROR, f"Unknown foreign state '{state_name}' in minion '{minion_name}'")
                else:
                    self.log(logging.ERROR, f"Dead minion '{minion_name}' or errors in connecting to its shared buffer")
            else:
                self.log(logging.ERROR, f"Unknown minion: '{minion_name}'")
        else:
            self.log(logging.DEBUG, f'Access denied because of the changed PID ({self._pid}->{pid})')

    def set_state(self, state_name: str, state_val):
        self.set_state_to(self.name, state_name, state_val)

    def get_foreign_buffer(self, minion_name, buffer_name):
        """
        Get value stored in the foreign shared buffer

        :param minion_name: Foreign minion's name
        :param buffer_name: Foreign minion's buffer's name

        :return:
            obj: the value store in the shared buffer
        """

        buffer_val = None

        pid, pid_checked = self.pid_check()
        if pid_checked:
            shared_buffer_reference_name = f"b*{minion_name}_{buffer_name}"
            if shared_buffer_reference_name in self._shared_dict.keys():
                shared_buffer_name = self._shared_dict[shared_buffer_reference_name]
                tmp_buffer: SharedBuffer
                if self.is_buffer_alive(minion_name, buffer_name):
                    with SharedDict(shared_buffer_name, lock=self.lock, create=False) as tmp_buffer:
                        buffer_val = tmp_buffer.read()
                else:
                    self.log(logging.ERROR, f"Invalid buffer '{minion_name}_{buffer_name}' or errors in connections")
            else:
                self.log(logging.ERROR, f"Unknown buffer: '{shared_buffer_reference_name}'")
        else:
            self.log(logging.DEBUG, f'Access denied because of the changed PID ({self._pid}->{pid})')

        return buffer_val

    def set_foreign_buffer(self, minion_name: str, buffer_name: str, val: object):
        """
        Overwrite the foreign shared buffer with the input value

        :param minion_name: Foreign minion's name
        :param buffer_name: Foreign minion's buffer's name
        :param val: New value to be stored in the buffer
        """
        pid, pid_checked = self.pid_check()
        if pid_checked:
            shared_buffer_reference_name = f"b*{minion_name}_{buffer_name}"
            if shared_buffer_reference_name in self._shared_dict.keys():
                shared_buffer_name = self._shared_dict[shared_buffer_reference_name]
                tmp_buffer: SharedBuffer
                with SharedDict(shared_buffer_name, lock=self.lock, create=False) as tmp_buffer:
                    try:
                        buffer_val = tmp_buffer.write(val)
                    except:
                        self.log(logging.ERROR, traceback.format_exc())
            else:
                self.log(logging.ERROR, f"Unknown buffer: '{shared_buffer_reference_name}'")
        else:
            self.log(logging.DEBUG, f'Access denied because of the changed PID ({self._pid}->{pid})')

    ############# Connection module #############

    def connect(self, minion: 'BaseMinion'):
        if minion._queue.get(self.name) is not None:
            self._queue[minion.name] = minion._queue[self.name]
        else:
            self._queue[minion.name] = Queue()
            minion.connect(self)
        # self.link_minion(minion.name)
        self.minion_to_link.append(minion.name)

    def disconnect(self, minion_name):
        k = [i for i in self._shared_dict.keys()]
        for i in k:
            if f"{minion_name}_" in i:
                self._shared_dict.pop(i)
        self._linked_minion.pop(minion_name)
        self._queue[minion_name].close()
        self._queue.pop(minion_name, 'None')

    ############# Pipe communication module #############

    def send(self, tgt_name, msg_val, msg_type=None):
        if self.status > 0:
            chn = self._queue[tgt_name]
            if chn is None:
                self.log(logging.ERROR, "Send failed: Queue [{}] does not exist".format(tgt_name))
                return None
            if not chn.full():
                chn.put((msg_val, msg_type))
            else:
                self.log(logging.WARNING, " Send failed: the queue for '{}' is fulled".format(tgt_name))
        else:
            self.log(logging.ERROR, "Send failed: '{}' has been terminated".format(tgt_name))
            self.disconnect(tgt_name)
            self.log(logging.INFO, "Removed invalid target {}".format(tgt_name))

    def get(self, src_name):
        chn = self._queue[src_name]
        if chn is None:
            self.log(logging.ERROR, "Receive failed: Queue [{}] does not exist".format(src_name))
            return None
        if self.status >= 0:
            if not chn.empty():
                received = chn.get()
            else:
                self.log(logging.DEBUG, "Empty Queue")
                received = None
        else:
            self.log(logging.ERROR, "Receive failed: '{}' has been terminated".format(self.name))
            received = None
            self.disconnect(src_name)
            self.log(logging.INFO, "Removed invalid source [{}]".format(src_name))

        if received is not None:
            msg_val = received[0]
            msg_type = received[1]
            return msg_val, msg_type
        else:
            return None, None

    ############# Status checking module #############

    @property
    def status(self):
        return self._shared_dict['status']

    @status.setter
    def status(self, value):
        self._shared_dict['status'] = value

    def is_minion_alive(self, minion_name: str):
        """
        Determine the states of connected foreign minion
        :param minion_name: Foreign minion's name
        :return:
            Bool or None: True if alive, False if dead, None if error
        """

        if minion_name in self._linked_minion.keys():
            try:
                with SharedDict(f"{minion_name}_shared_dict", lock=self.lock, create=False):
                    pass
                return True
            except FileNotFoundError:
                self.log(logging.DEBUG, f"Linked minion '{minion_name}' is dead. RIP")
                self.disconnect(minion_name)
                return False
            except Exception:
                self.log(logging.ERROR, f"Unknown error when checking {minion_name} status.\n{traceback.format_exc()}")
                return None
        else:
            self.log(logging.DEBUG, f"Minion '{minion_name}' is not connected")
            return None

    def is_buffer_alive(self, minion_name, buffer_name):
        """
        Determine the states of connected foreign shared buffer
        :param minion_name: Foreign minion's name
        :param buffer_name: Foreign minion's buffer's name
        :return:
            Bool or None: True if alive, False if dead, None if error
        """
        if minion_name in self._linked_minion.keys():
            try:
                with SharedDict(f"{minion_name}_{buffer_name}", lock=self.lock, create=False) as tmp_dict:
                    return tmp_dict.is_alive
            except FileNotFoundError:
                self.log(logging.INFO, f"Linked shared buffer '{minion_name}_{buffer_name}' is closed.")
                self._shared_dict.pop(f"b*{minion_name}_{buffer_name}")
                return False
            except Exception:
                self.log(logging.ERROR,
                         f"Unknown error when checking shared buffer '{minion_name}_{buffer_name}' status.\n{traceback.format_exc()}")
                return None
        else:
            print(f"Minion '{minion_name}' is not connected")
            return None

    def poll_minion(self, func: Callable = None):
        """
        Poll connected foreign minions' status
        :return:
            list: a list of connected minions' status
        """
        minion_names = [i for i in self._linked_minion.keys() if 'logger' not in i.lower()]
        minion_status = [None] * len(minion_names)
        for i, i_name in enumerate(minion_names):
            if func is not None:
                try:
                    func(i_name)
                except:
                    self.error('Error when executing custom function during polling')
                minion_status[i] = self.is_minion_alive(i_name)
        return minion_status

    ############# Housekeeping module #############

    def run(self):
        self.Process = mp.Process(target=BaseMinion.innerLoop, args=(self,))
        self.Process.start()

    def initialize(self):
        pass

    def init_process(self):
        pass

    def main(self):
        pass

    def shutdown(self):
        self.status = -1

    def _shutdown(self):
        if self.logger is not None:
            self.log(logging.INFO, self.name + " is off")
            self.status = -2
        for i in list(self._queue.keys()):
            self.disconnect(i)
        for i in list(self._queue.keys()):
            self.disconnect(i)

        bv: SharedBuffer
        for bk, bv in self._shared_buffer:
            bv.terminate()
        self._shared_dict.terminate()

        # if self.Process._popen:
        #     self.Process.join()  # _popen is a protected attribute. Maybe test with .is_alive()?

        if self.Process.is_alive():
            self.Process.close()

    def watch_state(self, name, val):
        if name not in self._watching_state.keys():
            self._watching_state[name] = val
            return True
        else:
            changed = val != self._watching_state[name]
            self._watching_state[name] = val
            return changed


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
            record.processName = '%s (for %s)' % (mp.current_process().name, record.processName)
            logger.handle(record)


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
        # self.name = name
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

    def set_level(self, logger_name, level):
        level = level.upper()
        if level in LOG_LVL_LOOKUP_TABLE.keys():
            logLevel = LOG_LVL_LOOKUP_TABLE[level]
            logger = logging.getLogger(logger_name)
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


class TimerMinion(BaseMinion):

    def __init__(self, *args, refresh_interval=10, **kwargs):
        super(TimerMinion, self).__init__(*args, **kwargs)
        self.timer = {'default': [-1,-1]}  # 1. interval, 2. elapsed time, 3. init_time
        self.timer_cb_func = {'default': self.on_time}
        self._isrunning = False
        self._interval = refresh_interval / 1000

    @property
    def refresh_interval(self):
        return self._interval*1000

    @refresh_interval.setter
    def refresh_interval(self, val):
        self._interval = val/1000

    def add_timer(self, name, cb_func=None):
        '''
        allows to add custom timer
        :param name: timer's name
        :return:
        '''
        self.timer[name] = [-1,-1]
        self.timer_cb_func[name] = cb_func

    def add_callback(self, timer_name, cb_func):
        if timer_name in self.timer_cb_func.keys():
            if self.timer_cb_func.get(timer_name) is not None:
                self.warning(f'Reset the callback function of the ["{timer_name}"] timer')
            self.timer_cb_func[timer_name] = cb_func
        else:
            self.error(f'NameError: Unknown timer name: {timer_name}')

    def start_timing(self, timer_name='default'):
        cur_time = perf_counter()
        if type(timer_name) is str:
            if timer_name == 'all':
                for k in self.timer.keys():
                    self.timer[k] = [0, cur_time]
            else:
                if timer_name in self.timer.keys():
                    self.timer[timer_name] = [0, cur_time]
                else:
                    self.error(f'NameError: Unknown timer name: {timer_name}')
        elif type(timer_name) is list:
            for n in timer_name:
                if n in self.timer.keys():
                    self.timer[n] = [0, cur_time]
                else:
                    self.error(f'NameError: Unknown timer name: {n}')
        else:
            self.error(f'TypeError: Invalid timer name: {timer_name}')

    def stop_timing(self, timer_name='default'):
        cur_time = perf_counter()
        if type(timer_name) is str:
            if timer_name == 'all':
                for k in self.timer.keys():
                    elapsed, init_time = self.timer[k]
                    self.timer[k] = [elapsed - init_time, -1]
            else:
                if timer_name in self.timer.keys():
                    elapsed, init_time = self.timer[timer_name]
                    self.timer[timer_name] = [elapsed - init_time, -1]
                else:
                    self.error(f'NameError: Unknown timer name: {timer_name}')
        elif type(timer_name) is list:
            for n in timer_name:
                if n in self.timer.keys():
                    elapsed, init_time = self.timer[n]
                    self.timer[n] = [elapsed - init_time, -1]
                else:
                    self.error(f'NameError: Unknown timer name: {n}')
        else:
            self.error(f'TypeError: Invalid timer name: {timer_name}')

    def exec(self):
        cur_time = perf_counter()
        for k,v in self.timer.items():
            if v[1] >= 0:
                elapsed = cur_time - v[1]
                if elapsed-v[0] > self._interval:
                    v[0] = elapsed
                    cb_func = self.timer_cb_func.get(k)
                    if cb_func is not None:
                        cb_func(v[0])

    def get_time(self, timer_name='default'):
        cur_time = perf_counter()
        if type(timer_name) is str:
            if timer_name == 'all':
                tmp_times = []
                for k,v in self.timer.items():
                    elapsed = cur_time - v[1]
                    if elapsed-v[0] > self._interval:
                        v[0] = elapsed
                        # cb_func = self.timer_cb_func.get(k)
                        # if cb_func is not None:
                        #     cb_func(v[0])
                    tmp_times.append(v)
                return tmp_times
            else:
                if timer_name in self.timer.keys():
                    elapsed = cur_time - self.timer[timer_name][1]
                    if elapsed - self.timer[timer_name][0] > self._interval:
                        self.timer[timer_name][0] = elapsed
                        # cb_func = self.timer_cb_func.get(timer_name)
                        # if cb_func is not None:
                        #     cb_func(elapsed)
                    return self.timer[timer_name]
                else:
                    self.error(f'NameError: Unknown timer name: {timer_name}')
                    return None
        elif type(timer_name) is list:
            tmp_times = []
            for n in timer_name:
                if n in self.timer.keys():
                    elapsed = cur_time - self.timer[timer_name][1]
                    if elapsed - self.timer[n][0] > self._interval:
                        self.timer[n][0] = elapsed
                        # cb_func = self.timer_cb_func.get(n)
                        # if cb_func is not None:
                        #     cb_func(self.timer[n][0])
                    tmp_times.append(self.timer[n])
                else:
                    self.error(f'NameError: Unknown timer name: {n}')
                    tmp_times.append(None)
            return tmp_times
        else:
            self.error(f'TypeError: Invalid timer name: {timer_name}')
            return None

    def initialize(self):
        self.start_timing('default')

    def main(self):
        self.exec()

    @property
    def elapsed(self):
        return self.get_time('default')[1]

    def on_time(self,t):
        pass


class AbstractMinionMixin:
    '''
    This class should serve as an interface between Qt window and minion process handler,
    All interaction rules between the two components should be defined here
    '''
    _processHandler: BaseMinion

    def log(self, level, msg):
        '''
        :param level: str; "DEBUG","INFO","WARNING","ERROR","CRITICAL"
        :param msg: str, log message
        '''

        level = level.upper()
        if level in LOG_LVL_LOOKUP_TABLE.keys():
            self._processHandler.log(LOG_LVL_LOOKUP_TABLE[level], msg)
        else:
            self._processHandler.debug(f"Logging failed, unknown logging level: {level}")

    def debug(self,msg):
        self._processHandler.debug(msg)

    def info(self,msg):
        self._processHandler.info(msg)

    def warning(self, msg):
        self._processHandler.warning(msg)

    def error(self, msg):
        self._processHandler.error(msg)

    def send(self, target: str, msg_type: str, msg_val):
        """
        :param target: string, the minion name to call
        :param msg_type: string or tuple of string: type reference
        :param msg_val: the content of the message, must be pickleable
        """
        self._processHandler.send(target, msg_type=msg_type, msg_val=msg_val)
        self.log("DEBUG", f"Sending message to [{target}],type: {msg_type}")

    def get(self, source: str):
        msg, msg_type = self._processHandler.get(source)
        if msg is not None:
            if msg_type is not None:
                self.log("DEBUG", f"Received message from [{source}] (type: {msg_type})")
            else:
                self.log("DEBUG", f"Received message from [{source}] (type: UNKNOWN)")
            self.parse_msg(msg_type, msg)
        else:
            self.log("DEBUG", f"EMPTY MESSAGE from [{source}]")

    def get_linked_minion_names(self):
        return list(self._processHandler._linked_minion.keys())

    def get_shared_state_names(self,minion_name):
        return list(self._processHandler.get_shared_state_names(minion_name))

    def create_state(self, state_name, state_val):
        self._processHandler.create_state(state_name, state_val)

    def remove_state(self, state_name):
        self._processHandler.remove_state(state_name)

    def set_state(self, state_name, state_val):
        self._processHandler.set_state(state_name, state_val)

    def set_state_to(self, minion_name, state_name, state_val):
        self._processHandler.set_state_to(minion_name, state_name, state_val)

    def get_state(self, state_name):
        return self._processHandler.get_state(state_name)

    def get_state_from(self, minion_name, state_name):
        return self._processHandler.get_state_from(minion_name, state_name)

    def parse_msg(self, msg_type, msg):
        pass

    def watch_state(self,name,val):
        return self._processHandler.watch_state('C_'+name,val)  # 'C_' for compiler states

    def shutdown(self):
        self._processHandler.shutdown()

    def status(self):
        return self._processHandler.status

class TimerMinionMixin(AbstractMinionMixin):

    def has_timer(self,name):
        self._processHandler: TimerMinion
        return name in self._processHandler.timer.keys()

    def add_timer(self,name,cb_func=None):
        self._processHandler.add_timer(name,cb_func)

    def start_timing(self,timer_name='default'):
        self._processHandler.start_timing(timer_name)

    def stop_timing(self,timer_name='default'):
        self._processHandler.stop_timing(timer_name)

    def get_time(self,timer_name='default'):
        return self._processHandler.get_time(timer_name)

    def elapsed(self):
        return self._processHandler.elapsed

    def timerInterval(self):
        self._processHandler:TimerMinion
        return self._processHandler.refresh_interval

    def setTimerInterval(self,val):
        self._processHandler.interval = val

