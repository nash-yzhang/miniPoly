import multiprocessing as mp
import traceback

import json
from multiprocessing import Queue, shared_memory
import warnings
from time import sleep, time
import logging
import logging.config
from logging import DEBUG, INFO, WARNING, ERROR, CRITICAL
from logging.handlers import QueueListener
from copy import deepcopy

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
        self._lock = 0  # Non-negative integer

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
                        raise ValueError(
                            f'[{self._CLASS_NAME} - {self._name}] Input memory size ({size}) is smaller than the '
                            f'actual data size ({nbytes_data}).')
                    else:
                        self._size = size

            self._size += self._READ_OFFSET
            self._shared_memory = shared_memory.SharedMemory(create=True, name=self._name, size=self._size)
            try:
                if byte_data is not None:
                    self.write(data)
                else:
                    self.valid_size = 0
            except Exception:
                print(traceback.format_exc())
                self.close()
                raise Exception(f'[{self._CLASS_NAME} - {self._name}] Unknown error in writing data')
        else:
            self._shared_memory = shared_memory.SharedMemory(name=self._name)
            self._size = self._shared_memory.size
            try:
                identity_string = self._read(-self._READ_OFFSET, self._READ_OFFSET, sudo=True).split('~')
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
                else:
                    warnings.warn('No data has been written into the buffer according to the [force_write] option')
            except Exception:
                print(traceback.format_exc())
                self.close()
                raise Exception(f'[{self._CLASS_NAME} - {self._name}] Unknown error in writing data')

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

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
                offset_list.append(loc + offset_loc)
                offset_loc = loc + len(byte_data)
                bytes_to_search = bytes_to_search[(offset_loc - offset):]
                iter += 1
            else:
                break

        return offset_list

    @property
    def name(self):
        return self._name

    @property
    def size(self):
        return self._size - self._READ_OFFSET

    @property
    def valid_size(self):
        return self._valid_size

    @valid_size.setter
    def valid_size(self, val):
        self._valid_size = val
        s_val = str(val)
        place_holder = '~' * (self._READ_OFFSET - len(self._CLASS_NAME + s_val) - 2)
        data = self._CLASS_NAME + place_holder + s_val
        byte_data = json.dumps(data).encode('utf-8')
        self._shared_memory.buf[:self._READ_OFFSET] = byte_data

    @property
    def free_space(self):
        return self.size - self.valid_size

    def read(self):
        return self._read(0, self.valid_size)

    def _read(self, offset, length, mode='obj',sudo=False):
        if sudo:
            lock_gained = True
        else:
            lock_gained = self.request_lock()
        if lock_gained:
            offset += self._READ_OFFSET
            _decoded_bytes = bytes(self._shared_memory.buf[offset:(offset + length)])
            if mode == 'obj':
                _decoded_bytes = _decoded_bytes.decode('utf-8').split('\x00')[0]
                if _decoded_bytes:
                    if not sudo:
                        self._mem_release()
                    return json.loads(_decoded_bytes)
                else:
                    if not sudo:
                        self._mem_release()
                    return _decoded_bytes
            elif mode == 'bytes':
                if not sudo:
                    self._mem_release()
                return _decoded_bytes
            else:
                if not sudo:
                    self._mem_release()
                raise ValueError(f'[{self._CLASS_NAME} - {self._name}] Undefined reading mode {mode}')
        else:
            raise TimeoutError(f'[{self._CLASS_NAME} - {self._name}]: Cannot get the read lock')

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

    def _mem_lock(self):
        if self.valid_size > -1:
            self._lock = self._valid_size * 1  # Make sure the value is copied
            self.valid_size = -1

    def _mem_release(self):
        self.valid_size = self._lock * 1  # Make sure the value is copied
        self._lock = 0

    def request_lock(self, timeout: int = 10000):
        itt = 0
        while itt < timeout:
            self._mem_lock()
            itt += 1
            if self._lock > -1:
                break

        return self._lock > -1

    def _set(self, byte_data, offset):
        if self.request_lock():
            if offset > max(self._lock - 1, 0):
                self._mem_release()
                raise IndexError(
                    f'[{self._CLASS_NAME} - {self._name}] Offset ({offset}) out of range: ({self._lock - 1})')  # To make sure all binary contents are continuous and no gap (b'\x00') in between

            if (offset + len(byte_data)) > self._size:
                self._mem_release()
                raise ValueError(
                    f'[{self._CLASS_NAME} - {self._name}] Data byte end position out of range (Offset: {offset}, Length: {len(byte_data)}). \nCheck if the data size is smaller than the buffer size')
            else:
                length = len(byte_data)

            offset += self._READ_OFFSET  # Protect the identity and size info block

            self._shared_memory.buf[offset:(offset + length)] = byte_data

            if offset + length > self._lock:
                self._lock = offset + length

            self._mem_release()
        else:
            raise TimeoutError(f'[{self._CLASS_NAME} - {self._name}]: Cannot get the write lock')

    def close(self):
        self._shared_memory.close()

    def terminate(self):
        try:
            self.clean()
        except:
            warnings.warn(traceback.format_exc())
        self._shared_memory.close()
        self._shared_memory.unlink()
        if self.is_alive():
            warnings.warn(f"An unknown error occurred that caused the SharedBuffer {self.name} cannot be destroyed.")

    # def __del__(self):
    #     self.terminate()

    def is_alive(self):
        try:
            tmp_buffer = SharedBuffer(self.name, create=False)
            tmp_buffer.close()
            return True
        except FileNotFoundError:
            return False


class SharedDict(dict):
    _BUFFER_PREFIX = 'b*'

    def __init__(self, linked_memory_name: str, *args, create=False, force_write=False, size=2 ** 14, **kwargs):
        super().__init__(*args, **kwargs)
        self._init_param = {"name": linked_memory_name,
                            "data": dict(self),
                            "create": create,
                            "force_write": force_write,
                            "size": size}
        self._linked_SharedBuffer = SharedBuffer(**self._init_param)
        self.is_alive = True

    def __setitem__(self, key, value):
        if self._BUFFER_PREFIX in key.lower():
            if key in self.keys():
                raise Exception(f'The item [{key}] cannot be modified/deleted as it is linked with a buffer.')

        super().__setitem__(key, value)
        try:
            self._linked_SharedBuffer.write(dict(self))
        except Exception:
            print(traceback.format_exc())

    def __getitem__(self, key):
        self._refresh()
        return super().__getitem__(key)

    def __repr__(self):
        self._refresh()
        return super().__repr__()

    def __delitem__(self, key):
        if self._BUFFER_PREFIX in key.lower():
            raise Exception(f'The item [{key}] cannot be modified/deleted as it is linked with a buffer.')
        super().__delitem__(key)
        if self._picklified:
            self.depiklify()
        self._linked_SharedBuffer.write(dict(self))

    # def __del__(self):
    #     self.close()

    def __enter__(self):
        self._refresh()
        return self

    def __exit__(self, *args):
        self.close()

    def _refresh(self):
        self._clear()
        try:
            self._update(self._linked_SharedBuffer.read())
        except:
            print(traceback.format_exc())

    def _update(self, D, **kwargs):
        super().update(D, **kwargs)

    def _clear(self):
        super().clear()

    def get(self, key):
        self._refresh()
        return super().get(key)

    def update(self, D: dict, **kwargs):
        self._refresh()
        for k, v in D.items():
            if self._BUFFER_PREFIX in k:
                D.pop(k)
        self._update(D)
        self._linked_SharedBuffer.write(dict(self))

    def clear(self, clear_buffer=False):
        self._clear()
        if clear_buffer:
            self._linked_SharedBuffer.write(dict(self))
        else:
            warnings.warn('SharedDict.clear() only clear its local dictionary items but not the linked shared buffer.\n'
                          'Set clear_buffer to True in order to clear the linked buffer')

    def pop(self, key):
        self._refresh()
        val = super().pop(key)
        self._linked_SharedBuffer.write(dict(self))
        return val

    def popitem(self):
        self._refresh()
        val = super().popitem()
        self._linked_SharedBuffer.write(dict(self))
        return val

    def copy(self):
        self._refresh()
        return super().copy()

    def items(self):
        self._refresh()
        return super().items()

    def keys(self):
        self._refresh()
        return super().keys()

    def values(self):
        self._refresh()
        return super().values()

    @property
    def buffer_dict(self):
        self._refresh()
        buffer_dict = {}
        for k, v in self.items():
            if self._BUFFER_PREFIX in k:
                buffer_dict[k] = v
        return buffer_dict

    def buffer_items(self):
        return self.buffer_dict.items()

    def buffer_keys(self):
        return self.buffer_dict.keys()

    def buffer_value(self):
        return self.buffer_dict.values()

    def unlink(self, key):
        if self._BUFFER_PREFIX in key:
            super().__delitem__(key)
            self._linked_SharedBuffer.write(dict(self))
            print(f'The link to the buffer [{key}] has been closed')
        else:
            raise Exception(f'The buffer [{key}] cannot be found.')

    def close(self):
        try:
            self._linked_SharedBuffer.close()
            self.is_alive = False
        except:
            print(traceback.format_exc())

    def terminate(self):
        try:
            self._linked_SharedBuffer.terminate()
            self.is_alive = False
        except:
            print(traceback.format_exc())


class BaseMinion:
    @staticmethod
    def innerLoop(hook: 'BaseMinion'):
        '''
        A dirty way to put BaseMinion as a listener when suspended
        :param hook: Insert self as a hook for using self logger, main process and shutdown method
        :return:
        '''
        hook.prepare_shared_buffer()
        hook.build_init_conn()
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

    _INDEX_SHARED_BUFFER_SIZE = 2 ** 16  # The size allocated for storing small shared values/array, each write takes <2 ms

    def __init__(self, name):
        self.name = name
        self._queue = {}  # a dictionary of in/output channels storing rpc function name-value pair (marshalled) E.g.: {'receiver_minion_1':('terminate',True)}
        self._log_config = None
        self._is_suspended = False
        self.logger = None
        self._shared_dict = None
        self._elapsed = time()

        # The _shared_buffer is a dictionary that contains the shared buffer which will be dynamically created and
        # destroyed. The indices of all shared memories stored in this dictionary will be saved in a dictionary
        # called _shared_buffer_index_dict, whose content will be updated into the _shared_buffer.
        self._shared_buffer = {}
        self._linked_minion = {}
        self.minion_to_link = []

    ############# Logging module #############
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

    ############# shared buffer/state module #############
    def prepare_shared_buffer(self):
        self._shared_dict = SharedDict(f'{self.name}_shared_dict', create=True, name=self.name,
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

        shared_buffer_name = f"{self.name}_{name}"
        shared_buffer_reference_name = f"b*{shared_buffer_name}"
        if shared_buffer_reference_name not in self._shared_dict.keys():
            try:
                self._shared_buffer[shared_buffer_name] = SharedBuffer(shared_buffer_name, data, size,
                                                                       create=True)  # The list '_shared_buffer" host all local buffer for other minion to access, it also serves as a handle hub for later closing these buffers
            except Exception:
                self.log(logging.ERROR, f"Error in creating buffer '{shared_buffer_name}'.\n{traceback.format_exc()}")
            self._shared_dict[shared_buffer_reference_name] = shared_buffer_name
        else:
            self.log(logging.ERROR, f"SharedBuffer '{shared_buffer_name}' already exist")

    def link_minion(self, minion_name):
        shared_buffer_name = f"{minion_name}_shared_dict"
        shared_buffer_reference_name = f"b*{shared_buffer_name}"
        if shared_buffer_reference_name not in self._shared_dict.keys():
            try:
                with SharedDict(
                        shared_buffer_name) as tmp_dict:  # Just to test if the SharedDict exist and the name is correct
                    dict_name = tmp_dict['name']
                    if dict_name == minion_name:
                        self.log(logging.INFO, f"Successfully connected to '{minion_name}.")
                        self._shared_dict[shared_buffer_reference_name] = shared_buffer_name
                        self._linked_minion[minion_name] = [
                            'shared_dict']  # The name of the shared buffer from this minion
                        return 1
                    else:
                        self.log(logging.ERROR,
                                 f'The "name" state of the linked shared buffer {dict_name} is inconsistent with input minion name {minion_name}.')
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

    def link_foreign_buffer(self, minion_name, buffer_name):
        shared_buffer_reference_name = f"b*{minion_name}_{buffer_name}"

        if shared_buffer_reference_name not in self._shared_dict.keys():
            if minion_name in self._linked_minion.keys():
                with SharedDict(f"{minion_name}_shared_dict", create=False) as tmp_dict:
                    if shared_buffer_reference_name in tmp_dict.keys():
                        self._shared_dict[shared_buffer_reference_name] = tmp_dict[shared_buffer_reference_name]
                    else:
                        self.log(logging.ERROR, f"Unknown foreign buffer '{buffer_name}' in minion '{minion_name}'")
                self._linked_minion[minion_name].append(buffer_name)  # The name of the shared buffer from this minion
            else:
                self.log(logging.ERROR, f"Unknown minion: '{minion_name}'")

        else:
            self.log(logging.INFO, f"Already linked to the foreign buffer {buffer_name} from minion {minion_name}")

    def is_minion_alive(self, minion_name):
        if minion_name in self._linked_minion.keys():
            try:
                with SharedDict(f"{minion_name}_shared_dict", create=False):
                    pass
                return True
            except FileNotFoundError:
                self.log(logging.INFO, f"Linked minion '{minion_name}' is dead. RIP")
                self.disconnect(minion_name)
                return False
            except Exception:
                self.log(logging.ERROR, f"Unknown error when checking {minion_name} status.\n{traceback.format_exc()}")
                return None
        else:
            print(f"Minion '{minion_name}' is not connected")
            return None

    def is_buffer_alive(self, minion_name, buffer_name):
        if minion_name in self._linked_minion.keys():
            try:
                with SharedDict(f"{minion_name}_{buffer_name}", create=False) as tmp_dict:
                    return tmp_dict.is_alive()
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

    def get_state_from(self, minion_name, state_name):
        state_val = None  # Return None if exception to avoid error
        if minion_name == self.name:
            if state_name in self._shared_dict.keys():
                state_val = self._shared_dict.get(state_name)
            else:
                self.log(logging.ERROR, f"Unknown state: '{state_name}'")

        elif minion_name in self._linked_minion.keys():
            if self.is_minion_alive(minion_name):
                with SharedDict(f"{minion_name}_shared_dict", create=False) as tmp_dict:
                    if state_name in tmp_dict.keys():
                        state_val = tmp_dict[state_name]
                    else:
                        self.log(logging.ERROR, f"Unknown foreign state '{state_name}' in minion '{minion_name}'")
            else:
                self.log(logging.ERROR, f"Dead minion '{minion_name}' or errors in connecting to its shared buffer")
        else:
            self.log(logging.ERROR, f"Unknown minion: '{minion_name}'")

        return state_val  # return None if any error

    def set_state_to(self, minion_name, state_name, val):

        if minion_name == self.name:
            if state_name in self._shared_dict.keys():
                self._shared_dict[state_name] = val
            else:
                self.log(logging.ERROR, f"Unknown state: '{state_name}'")

        elif minion_name in self._linked_minion.keys():
            if self.is_minion_alive(minion_name):
                with SharedDict(f"{minion_name}_shared_dict", create=False) as tmp_dict:
                    if state_name in tmp_dict.keys():
                        tmp_dict[state_name] = val
                    else:
                        self.log(logging.ERROR, f"Unknown foreign state '{state_name}' in minion '{minion_name}'")
            else:
                self.log(logging.ERROR, f"Dead minion '{minion_name}' or errors in connecting to its shared buffer")
        else:
            self.log(logging.ERROR, f"Unknown minion: '{minion_name}'")

        return None  # return None if any error

    def get_foreign_buffer(self, minion_name, buffer_name):
        buffer_val = None

        shared_buffer_reference_name = f"b*{minion_name}_{buffer_name}"
        if shared_buffer_reference_name in self._shared_dict.keys():
            shared_buffer_name = self._shared_dict[shared_buffer_reference_name]
            tmp_buffer: SharedBuffer
            if self.is_buffer_alive(minion_name, buffer_name):
                with SharedDict(shared_buffer_name, create=False) as tmp_buffer:
                    buffer_val = tmp_buffer.read()
            else:
                self.log(logging.ERROR, f"Invalid buffer '{minion_name}_{buffer_name}' or errors in connections")
        else:
            self.log(logging.ERROR, f"Unknown buffer: '{shared_buffer_reference_name}'")

        return buffer_val

    def set_foreign_buffer(self, minion_name, buffer_name, val):
        shared_buffer_reference_name = f"b*{minion_name}_{buffer_name}"
        if shared_buffer_reference_name in self._shared_dict.keys():
            shared_buffer_name = self._shared_dict[shared_buffer_reference_name]
            tmp_buffer: SharedBuffer
            with SharedDict(shared_buffer_name, create=False) as tmp_buffer:
                try:
                    buffer_val = tmp_buffer.write(val)
                except:
                    self.log(logging.ERROR, traceback.format_exc())
        else:
            self.log(logging.ERROR, f"Unknown buffer: '{shared_buffer_reference_name}'")

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
        if self.status > 0:
            if not chn.empty():
                received = chn.get()
            else:
                self.log(logging.DEBUG, "Empty Queue")
                received = None
        else:
            self.log(logging.ERROR, "Receive failed: '{}' has been terminated".format(src_name))
            received = None
            self.disconnect(src_name)
            self.log(logging.INFO, "Removed invalid source [{}]".format(src_name))

        if received is not None:
            msg_val = received[0]
            msg_type = received[1]
            return msg_val, msg_type
        else:
            return None, None

    @property
    def status(self):
        return self._shared_dict['status']

    @status.setter
    def status(self, value):
        self._shared_dict['status'] = value

    def run(self):
        self.Process = mp.Process(target=BaseMinion.innerLoop, args=(self,))
        self.Process.start()

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
        self.connect(reporter)
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
        self.set_state_to(self.name, "status", -1)


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
        :param msg_type: string or tuple of string: type reference
        :param msg_val: the content of the message, must be pickleable
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
