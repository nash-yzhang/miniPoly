import os
from time import sleep, time, perf_counter

import multiprocessing as mp
from multiprocessing import Queue

import logging
import logging.config
from logging import DEBUG, INFO, WARNING, ERROR, CRITICAL

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

    _INDEX_SHARED_BUFFER_SIZE = 2 ** 13  # The size allocated for storing small shared values/array, each write takes <2 ms

    def __init__(self, name):

        self.logger = None
        self._log_config = None
        self.Process = None
        self._shared_dict = None
        self._is_suspended = False
        self._pid = None

        self.name = name
        self._status_name = f"b*{self.name}_status"
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

    def prepare_shared_buffer(self):
        self._shared_dict = SharedDict(f'{self.name}_shared_dict', lock=self.lock, create=True, name=self.name,
                                       size=self._INDEX_SHARED_BUFFER_SIZE)
        self.create_state('status', 1, use_buffer=True)  # create a shared state for the minion status which will be stored in an independent shared buffer
        self._shared_dict['name'] = self.name

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

    def create_shared_buffer(self, name, data, dtype=None):
        # The reference name of any shared buffer should have the structure 'b*{minion_name}_{buffer_name}' The
        # builtin state dictionary for all minions are the SharedDict whose name is 'b*{self.name}_shared_dict'
        # The names of all other buffers created later will be saved in the builtin SharedDict as a shared state as
        # name-value pairs: {shared_buffer_reference_name}: {shared_buffer_name};
        # #
        # For safety consideration, it is compulsory to use "with" statement to access any foreign buffers.

        if type(data) in [list, tuple]:
            data = np.array(data)
        elif type(data) in [int, float, bool]:
            data = np.array([data], dtype = type(data))
        elif type(data) == np.ndarray:
            pass
        else:
            raise TypeError(f"Data type {type(data)} is not supported")
        if dtype is not None:
            data = data.astype(dtype)

        if name not in self._shared_dict.keys():
            shared_buffer_name = f"{self.name}_{name}"
            try:
                self._shared_buffer[f"b*{shared_buffer_name}"] = SharedNdarray(shared_buffer_name, self.lock, data)  # The list '_shared_buffer" host all local buffer for other minion to access, it also serves as a handle hub for later closing these buffers
            except Exception:
                self.log(logging.ERROR, f"Error in creating buffer '{name}'.\n{traceback.format_exc()}")
            self._shared_dict[name] = f"b*{shared_buffer_name}"  # e.g. 'status': 'b*{self.name}_status' -> 'b*{self.name}_status': '{self.name}_status'
        else:
            self.log(logging.ERROR, f"SharedBuffer '{name}' already exist")

    def remove_shared_buffer(self,state_name: str):
        if state_name in self._shared_buffer.keys():
            self._shared_buffer[state_name].close()
            del self._shared_buffer[state_name]
        else:
            self.log(logging.ERROR, f"State '{state_name}' cannot be deleted because it does not exist")

    def link_minion(self, minion_name):
        if minion_name not in self._linked_minion.keys():
            try:
                shared_buffer_name = f"{minion_name}_shared_dict"
                with SharedDict(shared_buffer_name, lock=self.lock) as tmp_dict:
                    # Test if the SharedDict exist and the name is correct
                    dict_name = tmp_dict.get('name')
                    if dict_name is None:
                        dict_name = 'N/A'
                    if dict_name == minion_name:
                        self.log(logging.INFO, f"Successfully connected to '{minion_name}.")
                        self._linked_minion[minion_name] = ['shared_dict']  # The name of the shared buffer from this minion

                        # To register all shared buffer from the linked minion
                        # A default shared buffer is 'status'
                        for k,v in tmp_dict.items():
                            if type(v) == str:
                                if v.startswith('b*'):
                                    self._linked_minion[minion_name].append(k)
                        return 0
                    else:
                        self.log(logging.ERROR,
                                 f'[{self.name}] Pre-execution error: The "name" state of the linked shared buffer {dict_name} is inconsistent with input minion name {minion_name}.')
                        return 1
            except FileNotFoundError:
                self.log(logging.INFO, f"SharedDict '{minion_name} not found'.")
                return -1
            except:
                self.log(logging.ERROR, f"Error when connecting to '{minion_name}'.\n{traceback.format_exc()}")
                return 2
        else:
            self.log(logging.INFO, f"Already linked to minion: {minion_name}")
            return 0

    def create_state(self, state_name: str, state_val: object, use_buffer: bool = False, dtype=None):
        if state_name in self._shared_dict.keys():
            self.log(logging.ERROR, f"State '{state_name}' already exists")
        else:
            if use_buffer:
                self.create_shared_buffer(state_name, state_val, dtype=dtype)
            else:
                self._shared_dict[state_name] = state_val
            self.log(logging.INFO, f"Shared state: '{state_name}' created")

    def remove_state(self,state_name: str):
        if state_name in self._shared_dict.keys():
            del self._shared_dict[state_name]
            self.log(logging.INFO, f"Shared state: '{state_name}' DELETED")
        elif state_name in self._shared_buffer.keys():
            self._shared_buffer[state_name].close()
            del self._shared_buffer[state_name]
        else:
            self.log(logging.ERROR, f"State '{state_name}' cannot be deleted because it does not exist")

    def has_state(self, state_name: str):
        return state_name in self._shared_dict.keys()

    def has_foreign_state(self, minion_name, state_name):
        has_state = False
        if minion_name in self._linked_minion.keys():
            if state_name in self._linked_minion[minion_name]:
                has_state = True
            else:
                if self.is_minion_alive(minion_name):
                    with SharedDict(f"{minion_name}_shared_dict", lock=self.lock, create=False) as shared_dict:
                        has_state = state_name in list(shared_dict.keys())
                else:
                    self.error(f"Dead minion: '{minion_name}'")
        else:
            self.log(logging.ERROR, f"Unknown minion: '{minion_name}'")
            return has_state

    def get_shared_state_names(self,minion_name:str):
        '''
        Get the names of all shared states in the minion's shared dictionary
        Will soon be deprecated
        '''
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


    def get_state_from(self, minion_name: str, state_name: str):
        """
        Get the value stored in the shared dictionary of self or foreign minions by dict key
        :param minion_name: str, minion's name
        :param state_name: str, shared dictionary key
        :return:
            obj: None if any error occurs in the process
        """
        state_val = None
        if minion_name == self.name:
            state_val = self.get_state(state_name)
        elif minion_name in self._linked_minion.keys():
            state_val = self.get_foreign_state(minion_name, state_name)
        else:
            self.error(f"Unknown minion: '{minion_name}'")

        return state_val

    def get_state(self, state_name: str,  asis=False):
        # param asis: if true, then keep the format of the state (e.g. state is an integer stored in a ndarray buffer,
        # asis == True, the state will be return as a numpy array
        state_val = None  # Return None if exception to avoid error
        if state_name in self._shared_dict.keys():
            state_val = self._shared_dict.get(state_name)
            if type(state_val) == str:
                if state_val.startswith('b*'):
                    state_val = self._read_buffer_as_state(state_val,asis)
        elif state_name == 'ALL':
            state_val = dict(self._shared_dict)
            for i_state_name, i_state_val in state_val.items():
                if type(i_state_val) == str:
                    if i_state_val.startswith('b*'):
                        state_val[i_state_name] = self._read_buffer_as_state(i_state_val, asis)
        else:
            self.error(f"Unknown state: '{state_name}'")
        return state_val

    def get_foreign_state(self, minion_name, state_name, asis=False, timeout=3000):
        # param asis: if true, then keep the format of the state (e.g. state is an integer stored in a ndarray buffer,
        # asis == True, the state will be return as a numpy array
        state_val = None
        err_code = 0
        if self.is_minion_alive(minion_name):
            if state_name in self._linked_minion[minion_name]:
                state_val = self._read_foreign_buffer_as_state(minion_name, state_name, asis)
            else:
                for i in range(int(timeout/10)):
                    with SharedDict(f"{minion_name}_shared_dict", lock=self.lock, create=False) as shared_dict:
                        if state_name in shared_dict.keys():
                            state_val = shared_dict[state_name]
                            if type(state_val) == str:
                                if state_val.startswith('b*'):
                                    self._linked_minion[minion_name].append(state_name)
                                    state_val = self._read_foreign_buffer_as_state(minion_name, state_name, asis)
                        elif state_name == 'ALL':
                            state_val = dict(shared_dict)
                            for i_state_name, i_state_val in state_val.items():
                                if type(i_state_val) == str:
                                    if i_state_val.startswith('b*'):
                                        state_val[i_state_name] = self._read_foreign_buffer_as_state(minion_name, i_state_name, asis)
                        else:
                            err_code = 1
                    if err_code == 0:
                        break
                    else:
                        sleep(0.01)
        else:
            err_code = 2

        if err_code == 1:
            self.error(f"Unknown foreign state '{state_name}' in minion '{minion_name}'")
        elif err_code == 2:
            self.error(f"Dead minion '{minion_name}' or errors in connecting to its shared buffer")

        return state_val

    def _read_foreign_buffer_as_state(self, minion_name, state_name, asis):
        with SharedNdarray(f"{minion_name}_{state_name}", lock=self.lock, create=False) as shm:
            state_val = shm.read()
            if state_val.size == 1 and not asis:
                state_val = state_val[0]
            return state_val

    def _read_buffer_as_state(self, state_name, asis):
        state_val = self._shared_buffer[state_name].read()
        if state_val.size == 1 and not asis:
            state_val = state_val[0]
        return state_val

    def set_state_to(self, minion_name: str, state_name: str, val):
        """
        Set the value stored in the shared dictionary of self or foreign minions by dict key
        :param minion_name: str, minion's name
        :param state_name: str, shared dictionary key
        :param val: the value to be set
        """
        if minion_name == self.name:
            self.set_state(state_name, val)

        elif minion_name in self._linked_minion.keys():
            self.set_foreign_state(minion_name, state_name, val)

    def set_state(self, state_name: str, state_val):
        if state_name in self._shared_dict.keys():
            stored_value = self._shared_dict[state_name]
            state_type = 'dict_val'
            if type(stored_value) == str:
                if stored_value.startswith('b*'):
                    state_type = 'buffer'
                    state_name = stored_value

            if state_type == 'dict_val':
                self._shared_dict[state_name] = state_val
            elif state_type == 'buffer':
                self._shared_buffer[state_name].write(state_val)
        else:
            self.error(f"Unknown state: '{state_name}'")
        return state_val

    def set_foreign_state(self, minion_name, state_name, state_val):
        err_code = 0
        if self.is_minion_alive(minion_name):
            if state_name in self._linked_minion[minion_name]:
                with SharedNdarray(f"{minion_name}_{state_name}", lock=self.lock, create=False) as shm:
                    shm.write(state_val)
            else:
                with SharedDict(f"{minion_name}_shared_dict", lock=self.lock, create=False) as shared_dict:
                    if state_name in shared_dict.keys():
                        # In case the state has been changed to buffer type, this section will update the linked_minion list
                        stored_val = shared_dict[state_name]
                        state_type = 'dict_val'
                        if type(stored_val) == str:
                            if stored_val.startswith('b*'):
                                self._linked_minion[minion_name].append(state_name)
                                state_type = 'buffer'
                        if state_type == "dict_val":
                            shared_dict[state_name] = state_val
                        else:
                            with SharedNdarray(f"{minion_name}_{state_name}", lock=self.lock, create=False) as shm:
                                shm.write(state_val)
                    else:
                        err_code = 1
        else:
            err_code = 2

        if err_code == 1:
            self.error(f"Unknown foreign state '{state_name}' in minion '{minion_name}'")
        elif err_code == 2:
            self.error(f"Dead minion '{minion_name}' or errors in connecting to its shared buffer")

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
        return self._shared_buffer[self._status_name].read()

    @status.setter
    def status(self, value):
        self._shared_buffer[self._status_name].write(value)

    def is_minion_alive(self, minion_name: str):
        """
        Determine the states of connected foreign minion
        :param minion_name: Foreign minion's name
        :return:
            Bool or None: True if alive, False if dead, None if error
        """

        if minion_name in self._linked_minion.keys():
            try:
                with SharedNdarray(f"{minion_name}_status", lock=self.lock, create=False) as shm:
                    val = shm.read()
                    if val <= 0:
                        val = False
                    else:
                        val = True
            except FileNotFoundError:
                val = False
            except Exception:
                self.error(f"Unknown error when checking {minion_name} status.\n{traceback.format_exc()}")
                val = None
        else:
            self.error(f"Minion '{minion_name}' is not connected")
            val = None
        return val


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
                with SharedNdarray(f"{minion_name}_{buffer_name}", lock=self.lock, create=False) as tmp_dict:
                    ISALIVE = tmp_dict.is_alive()
                return ISALIVE
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
        for bk, bv in self._shared_buffer.items():
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


class TimerMinion(BaseMinion):

    def __init__(self, name, refresh_interval=10):
        super(TimerMinion, self).__init__(name)
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
    This class should serve as an compiler between Qt window and minion process handler,
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

    def create_state(self, state_name, state_val, use_buffer=False, dtype=None):
        self._processHandler.create_state(state_name, state_val, use_buffer, dtype)

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

    def create_shared_buffer(self, buffer_name, buffer_val):
        self._processHandler.create_shared_buffer(buffer_name, buffer_val)

    def remove_shared_buffer(self, buffer_name):
        self._processHandler.remove_shared_buffer(buffer_name)
    def has_foreign_state(self, minion_name, buffer_name):
        return self._processHandler.has_foreign_state(minion_name,buffer_name)

    def has_state(self, buffer_name):
        return self._processHandler.has_state(buffer_name)

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
