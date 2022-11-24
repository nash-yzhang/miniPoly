import multiprocessing as mp
import traceback

import numpy as np
import json
from multiprocessing import Value, Queue, shared_memory
import warnings
from time import sleep, time
import logging
import logging.config
from logging import DEBUG, INFO, WARNING, ERROR, CRITICAL
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

LOG_LVL_LOOKUP_TABLE = {
    "DEBUG": DEBUG,
    "INFO": INFO,
    "WARNING": WARNING,
    "ERROR": ERROR,
    "CRITICAL": CRITICAL,
}

COMM_WAITING_TIME = 1e-3


class SharedBuffer:
    '''
    Wrapper for multiprocessing.shared_memory
    '''
    _CLASS_NAME = 'SharedBuffer'
    _MAX_BUFFER_SIZE = 2 ** 32  # Maximum shared memory: 4 GB
    _READ_OFFSET = 30  # The first 30 bytes represents the valid size of the shared buffer

    def __init__(self, name, data=None, size=None, create=True, force_write=False):
        self._size = None
        self._name = name
        self._valid_size = 0  # The actual size with data loaded

        byte_data = None

        if create:
            if size is None:
                if data is None:
                    raise ValueError("'size' must be a positive number different from zero")
                else:
                    byte_data = json.dumps(data).encode('utf-8')
                    nbytes_data = len(byte_data)
                    self._size = min(nbytes_data * 2, self._MAX_BUFFER_SIZE)
            else:
                if size > self._MAX_BUFFER_SIZE:
                    raise ValueError(
                        f'[{self._CLASS_NAME} - {self._name}] Input size ({size // (2 ** 30)}GB) is larger than '
                        f'the maximum size (4GB) supported.')
                if data is None:
                    self._size = size
                else:
                    byte_data = json.dumps(data).encode('utf-8')
                    nbytes_data = len(byte_data)
                    if size < nbytes_data:
                        raise ValueError(f'[{self._CLASS_NAME} - {self._name}] Input memory size ({size}) is smaller than the '
                                         f'actual data size ({nbytes_data}).')
                    else:
                        self._size = min(nbytes_data * 2, self._MAX_BUFFER_SIZE)

            self._size += self._READ_OFFSET
            self._shared_memory = shared_memory.SharedMemory(create=True, name=self._name, size=self._size)
            try:
                if byte_data is not None:
                    self.write(data)
            except Exception:
                print(traceback.format_exc())
                self.close()
                raise Exception(f'[{self._CLASS_NAME} - {self._name}] Unknown error in writing data')
        else:
            self._shared_memory = shared_memory.SharedMemory(name=self._name)
            self._size = self._shared_memory.size
            try:
                identity_string = self._read(-self._READ_OFFSET,self._READ_OFFSET).split('~')
                if identity_string[0] != self._CLASS_NAME:
                    raise TypeError(f'[{self._CLASS_NAME} - {self._name}] Unsupported type of shared memory')
                else:
                    self._valid_size = int(identity_string[-1])
            except Exception:
                print(traceback.format_exc())
                self.close()
                raise TypeError(f'[{self._CLASS_NAME} - {self._name}] Unsupported type of shared memory')

            try:
                if force_write and data is not None:
                    self.write(data)
            except Exception:
                print(traceback.format_exc())
                self.close()
                raise Exception(f'[{self._CLASS_NAME} - {self._name}] Unknown error in writing data')


    def find(self, data, k=1, offset=0, length=None):
        '''
        :param data: picklable data that can be converted to bytes with json.dumps
        :param k: return the first k occurrence of the data
        :return: offsets: list of the occurrence positions
        '''
        iter = 0
        byte_data = json.dumps(data).encode('utf-8')
        if length is None:
            length = self.valid_size - offset
        bytes_to_search = self._read(offset=offset, length=length, mode='bytes')
        offset_list = []
        offset_loc = offset

        while iter < k:
            loc = bytes_to_search.find(byte_data)
            if loc > 0:
                offset_list.append(loc+offset_loc)
                offset_loc = loc+len(byte_data)
                bytes_to_search = bytes_to_search[(offset_loc-offset):]
                iter += 1
            else:
                break

        return offset_list

    @property
    def valid_size(self):
        return self._valid_size
    @valid_size.setter
    def valid_size(self,val):
        self._valid_size = val
        s_val = str(val)
        place_holder = '~'*(self._READ_OFFSET-len(self._CLASS_NAME+s_val)-2)
        data = self._CLASS_NAME + place_holder + s_val
        byte_data = json.dumps(data).encode('utf-8')
        self._shared_memory.buf[:self._READ_OFFSET] = byte_data


    def read(self):
        return self._read(0, self.valid_size)

    def _read(self, offset, length, mode='obj'):
        offset += self._READ_OFFSET
        _decoded_bytes = bytes(self._shared_memory.buf[offset:(offset + length)])
        if mode == 'obj':
            return json.loads(_decoded_bytes.decode('utf-8').split('\x00')[0])
        elif mode == 'bytes':
            return _decoded_bytes
        else:
            raise ValueError(f'[{self._CLASS_NAME} - {self._name}] Undefined reading mode {mode}')

    def read_bytes(self):
        return self._read(0, self.valid_size, mode='bytes')

    def write(self, data, mode='overwrite', offset=0):
        '''
        :param data: picklable data
        :param mode: If 'overwrite' (default), the input offset will be ignored.
                     All contents in the existing memory will be overwritten by the input data;
                     If 'modify', the bytes in [offset:nbytes(data)] will be changed by data

        :param offset: Only for mode == 'modify'. The start position in the buffer for the set operation
        :return:
        '''
        byte_data = json.dumps(data).encode('utf-8')
        if mode == 'overwrite':
            self.clean()
            self._set(byte_data, offset=0)
        elif mode == 'modify':
            self._set(byte_data, offset=offset)

    def clean(self):
        self._clean(0)

    def _clean(self, offset):
        self._set(b'\x00' * (self.valid_size - offset), offset=offset)  # delete everything after offset
        self.valid_size = offset

    def _set(self, byte_data, offset):

        if offset > max(self.valid_size - 1, 0):
            raise IndexError(
                f'[{self._CLASS_NAME} - {self._name}] Offset ({offset}) out of range: ({self.valid_size - 1})')  # To make sure all binary contents are continuous and no gap (b'\x00') in between

        if (offset + len(byte_data)) > self._size:
            raise ValueError(
                f'[{self._CLASS_NAME} - {self._name}] Data byte end position out of range (Offset: {offset}, Length: {len(byte_data)}). \nCheck if the data size is smaller than the buffer size')
        else:
            length = len(byte_data)

        offset += self._READ_OFFSET  # Protect the identity and size info block

        self._shared_memory.buf[offset:(offset + length)] = byte_data

        if offset + length > self.valid_size:
            self.valid_size = offset + length

    def close(self):
        self._shared_memory.close()
        self._shared_memory.unlink()

    def __del__(self):
        self.close()


class BaseMinion:
    @staticmethod
    def innerLoop(hook):
        '''
        A dirty way to put BaseMinion as a listener when suspended
        :param hook: Insert self as a hook for using self logger, main process and shutdown method
        :return:
        '''
        STATE = hook.status
        if hook._log_config is not None:
            logging.config.dictConfig(hook._log_config)
            hook.logger = logging.getLogger(hook.name)
        while STATE >= 0:
            if STATE == 1:
                if hook._is_suspended:
                    hook._is_suspended = False
                hook.main()
            elif STATE == 0:
                if not hook._is_suspended:
                    hook.info(hook.name + " is suspended\n")
                    hook._is_suspended = True
            STATE = hook.status
        hook._shutdown()

    def __init__(self, name):
        self.name = name
        self._conn = {}  # a dictionary of in/output channels storing rpc function name-value pair (marshalled) E.g.: {'receiver_minion_1':('terminate',True)}
        self._buffer = {}
        self._buffer_lookup_table = {}
        self._log_config = None
        self._is_suspended = False
        self._shared_memory = None
        self.logger = None
        self.shared_memory = {}
        self._shared_memory = {}
        self._elapsed = time()

    # def init_header_buffer(self):
    #     self._header_buffer = shared_memory.SharedMemory(create=True,name=self.name,size=proto_shared_memory.nbytes)

    def create_shared_memory(self, name, shape, dtype):
        proto_shared_memory = np.ndarray(shape=shape, dtype=dtype)
        self._shared_memory = shared_memory.SharedMemory(create=True, name=name, size=proto_shared_memory.nbytes)
        self._shared_memory_param = (name, shape, dtype)

    def add_connection(self, conn):
        if conn._conn.get(self.name) is not None:
            self._conn[conn.name] = conn._conn[self.name]
        else:
            self._conn[conn.name] = Queue()
            conn.add_connection(self)

    def del_connection(self, src_name):
        for key in list(self._buffer.keys()):
            if src_name in key:
                self._buffer.pop(key, 'None')
        self._conn[src_name].close()
        self._conn.pop(src_name, 'None')

    def send(self, tgt_name, msg_val, msg_type=None):
        if self.status > 0:
            chn = self._conn[tgt_name]
            if chn is None:
                self.log(logging.ERROR, "Send failed: Queue [{}] does not exist".format(tgt_name))
                return None
            if not chn.full():
                chn.put((msg_val, msg_type))
            else:
                self.log(logging.WARNING, " Send failed: the queue for '{}' is fulled".format(tgt_name))
        else:
            self.log(logging.ERROR, "Send failed: '{}' has been terminated".format(tgt_name))
            self.del_connection(tgt_name)
            self.log(logging.INFO, "Removed invalid target {}".format(tgt_name))

    def get(self, src_name):
        chn = self._conn[src_name]
        if chn is None:
            self.log(logging.ERROR, "Receive failed: Queue [{}] does not exist".format(src_name))
            return None
        if self.status > 0:
            if not chn.empty():
                received = chn.get()
            else:
                self.log(logging.DEBUG, "Empty Queue")
                received = None
        else:
            self.log(logging.ERROR, "Receive failed: '{}' has been terminated".format(src_name))
            received = None
            self.del_connection(src_name)
            self.log(logging.INFO, "Removed invalid source [{}]".format(src_name))

        if received is not None:
            msg_val = received[0]
            msg_type = received[1]
            return msg_val, msg_type
        else:
            return None, None

    @property
    def status(self):
        return self._buffer['{}_status'.format(self.name)]

    @status.setter
    def status(self, value):
        self._buffer['{}_status'.format(self.name)] = value

    @property
    def status_handle(self):
        return self._buffer['{}_status'.format(self.name)]

    @status_handle.setter
    def status_handle(self, value):
        self.log(logging.ERROR, "Status handle is a read-only property that cannot be changed")

    def link_shared_memory(self, buffer_name, shape, dtype):
        self._shared_memory[buffer_name] = shared_memory.SharedMemory(name=buffer_name)
        self.shared_memory.update(
            {buffer_name: np.ndarray(shape, dtype=dtype, buffer=self._shared_memory[buffer_name].buf)})
        self.shared_memory[buffer_name][:] = np.nan
        self._buffer['{}_{}'.format(buffer_name, 'status')] = self.shared_memory[buffer_name][0]

    def create_shared_state(self, minion_name: str, state_name: str, state_val=None):
        '''
        Create a shared state for a minion with registered shared memory
        :param minion_name: registered minion name
        :param state_name: shared state name
        :param state_val: (Optional) shared state value
        :return:
        '''
        try:
            buffer_loc = next(i for i, v in enumerate(self.shared_memory[minion_name]) if np.isnan(v))
        except StopIteration:
            self.log("No empty space on shared memory: [{}] for storing new state".format(minion_name))
            return None
        self._buffer['{}_{}'.format(self.name, state_name)] = self.shared_memory[self.name][buffer_loc]
        self._buffer_lookup_table['{}_{}'.format(self.name, state_name)] = buffer_loc
        if state_val is not None:
            self._buffer['{}_{}'.format(self.name, state_name)] = state_val

    # def create_shared_state(self, minion_name, buffer_name='all'):
    #     if minion_name not in self._conn.keys():
    #         self.log(logging.WARNING, "Registering buffer from an UNKNOWN minion {}".format(minion_name))
    #     # minion_shared_memory = minion.shared_memory[minion.name]
    #     # new_instance_buffer = shared_memory.SharedMemory(name=minion.name)
    #     # memory_handle = np.ndarray(minion_shared_memory.shape, dtype=minion_shared_memory.dtype, buffer=new_instance_buffer.buf)
    #     # self.shared_memory.update({minion.name: memory_handle})
    #
    #     if type(buffer_name) is str:
    #         if buffer_name == 'all':
    #             buffer_name_list = list(minion._buffer.keys())
    #         else:
    #             buffer_name_list = ['{}_{}'.format(minion.name, buffer_name)]
    #     elif type(buffer_name) is list:
    #         buffer_name_list = ['{}_{}'.format(minion.name,i) for i in buffer_name]
    #     else:
    #         self.log(logging.ERROR, "Invalid type of buffer name")
    #
    #     for iter_buffer_name in buffer_name_list:
    #         buffer_loc = minion._buffer_lookup_table[iter_buffer_name]
    #         if buffer_loc is None:
    #             self.log(logging.ERROR, "Unregistered buffer name {} in minion {}".format(buffer_name, minion.name))
    #         else:
    #             self._buffer[iter_buffer_name] = self.shared_memory[minion.name][buffer_loc]
    #             self._buffer_lookup_table[iter_buffer_name] = buffer_loc

    # def remote_register_shared_buffer(self,minion_name,buffer_name,timeout=1):
    #     if minion_name in self._conn.keys():
    #         self.send(minion_name, buffer_name, msg_type='request_buffer_handle')
    #         sent_time = time()
    #         while time()-sent_time < timeout:
    #             self.get(minion_name)
    #     else:
    #         self.log(logging.WARNING, "Access Denied in registering shared buffer: Minion {} is neither a source nor a target".format(minion.name))
    #     buffer_handle = minion.get_buffer(buffer_name)
    #     if buffer_handle is None:
    #         self.log(logging.ERROR, "Unregistered buffer name {} in minion {}".format(buffer_name, minion.name))
    #         return None
    #     self._buffer['{}_{}'.format(minion.name, buffer_name)] = buffer_handle

    def get_state(self, buffer_name):
        return self.get_buffer_from(self.name, buffer_name)

    def get_state_from(self, minion_name, buffer_name):
        i_buffer = self._buffer.get('{}_{}'.format(minion_name, buffer_name))
        if i_buffer is None:
            self.log(logging.ERROR, "Unregistered buffer name {} in minion {}".format(buffer_name, minion_name))
            return None
        else:
            return i_buffer

        # if minion_name is None:
        #     minion_name = self.name
        # return self._buffer['{}_{}'.format(minion_name, category)].value

    def set_state(self, minion_name, category, value):
        self._buffer['{}_{}'.format(minion_name, category)] = value

    # def get_state_handle(self, minion_name=None, category="status"):
    #     '''
    #     Only used as a shortcut for getting minion status
    #     :param minion_name: the name of the minion to get the state handle for
    #     :param category: state category
    #     :return:
    #     '''
    #     if minion_name is None:
    #         minion_name = self.name
    #     return self._buffer['{}_{}'.format(minion_name, category)]

    # def share_state_handle(self, minion_name, category, value):
    #     self._buffer.update({'{}_{}'.format(minion_name, category): value})

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

    def run(self):
        self.Process = mp.Process(target=BaseMinion.innerLoop, args=(self,))
        self.set_state(self.name, "status", 1)
        self.Process.start()

    def main(self):
        pass

    def shutdown(self):
        self.set_state(self.name, "status", -1)

    def _shutdown(self):
        if self.logger is not None:
            self.log(logging.INFO, self.name + " is off")
            self.set_state(self.name, "status", -2)
        for i in list(self._conn.keys()):
            self.del_connection(i)
        for i in list(self._conn.keys()):
            self.del_connection(i)
        if self.Process._popen:
            self.Process.join()


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
                'level': 'ERROR'
            }
        },
        'root': {
            'handlers': ['console', 'file', 'errors'],
            'level': 'DEBUG'
        }
    }

    def __init__(self, name, logger_config=DEFAULT_LOGGER_CONFIG, listener_config=DEFAULT_LISTENER_CONFIG):
        self.name = name
        super(LoggerMinion, self).__init__(name=self.name)
        logging.config.dictConfig(logger_config)
        self.logger = logging.getLogger(self.name)
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
            self.debug(f"Unknown logging level: {level}")

    def register_reporter(self, reporter):
        self.create_shared_state(reporter.name, "status")
        self.reporter.append(reporter.name)

    def poll_reporter(self):
        return all([self.get_state_from(i, 'status') == -2 for i in self.reporter])

    def main(self):
        if not self.hasConfig:
            logging.config.dictConfig(self.listener_config)
            self.hasConfig = True
        record = self.dequeue(True)
        self.handle(record)
        if self.poll_reporter():
            self.shutdown()

    def shutdown(self):
        while not self.queue.empty():
            record = self.dequeue(True)
            self.handle(record)
        self.set_state(self.name, "status", -1)


class AbstractMinionMixin:
    '''
    This class should serve as an interface between Qt window and minion process handler,
    All interaction rules between the two components should be defined here
    '''

    def log(self, level, msg):
        '''
        :param level: str; "DEBUG","INFO","WARNING","ERROR","CRITICAL"
        :param msg: str, log message
        :return: None
        '''

        level = level.upper()
        if level in LOG_LVL_LOOKUP_TABLE.keys():
            self._processHandler.log(LOG_LVL_LOOKUP_TABLE[level], msg)
        else:
            self._processHandler.debug(f"Logging failed, unknown logging level: {level}")

    def send(self, target: str, msg_type: str, msg_val):
        """
        :param target: string, the minion name to call
        :param msg: string or tuple of string
        :return:
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

    def parse_msg(self, msg_type, msg):
        pass
