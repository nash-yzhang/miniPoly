import json
import traceback
import warnings
from multiprocessing import shared_memory, Lock

import numpy as np


class SharedBuffer:
    _CLASS_NAME = 'SharedBuffer'
    _MAX_BUFFER_SIZE = 2 ** 24  # Maximum shared memory: 16 MB
    _READ_OFFSET = len(_CLASS_NAME) + 1  # The first 30 bytes represents the valid size of the shared buffer
    _LOCK_OFFSET = 1

    def __init__(self, name, lock, use_RWLock = False, data=None, size=None, create=True):
        self._size = None
        self._name = name
        self._lock = lock
        self.use_RWLock = use_RWLock

        byte_data = None

        if create:
            if size is None:
                if data is None:
                    raise ValueError("'size' must be a positive number different from zero")
                else:
                    byte_data = json.dumps(data).encode('utf-8')
                    nbytes_data = len(byte_data)
                    size = min(nbytes_data * 2 + self._READ_OFFSET + self._LOCK_OFFSET, self._MAX_BUFFER_SIZE)
            else:
                if data is not None:
                    byte_data = json.dumps(data).encode('utf-8')
                    nbytes_data = len(byte_data)
                    if size < nbytes_data:
                        raise ValueError(
                            f'[{self._CLASS_NAME} - {self._name}] Input memory size ({size}) is smaller than the '
                            f'actual data size ({nbytes_data}).')

            self._size = size + 0
            size += self._READ_OFFSET + self._LOCK_OFFSET

            if size > self._MAX_BUFFER_SIZE:
                raise ValueError(
                    f'[{self._CLASS_NAME} - {self._name}] Input size ({size // (2 ** 20)}MB) is larger than '
                    f'the maximum size (16 MB) supported.')
            else:
                self._shared_memory = shared_memory.SharedMemory(create=True, name=self._name, size=size)
                self._write_header()

            if data is not None:
                self.write(data)

        else:
            self._shared_memory = shared_memory.SharedMemory(name=self._name)
            self._size = self._shared_memory.size - (self._READ_OFFSET + self._LOCK_OFFSET)
            try:
                identity_string = self._read_header()
                if identity_string != self._CLASS_NAME:
                    raise TypeError(f'[{self._CLASS_NAME} - {self._name}] Unsupported type of shared memory')
            except Exception:
                print(traceback.format_exc())
                self.close()
                raise TypeError(f'[{self._CLASS_NAME} - {self._name}] Unsupported type of shared memory')
            # if data:
            #     self.write(data)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def _write_header(self):
        lock_acquired = self._lock.acquire(timeout=0.1)
        if not lock_acquired:
            warnings.warn(f'[{self._CLASS_NAME} - {self._name}] TIMEOUT ERROR; Failed to interact with shared memory')
        self._shared_memory.buf[:self._READ_OFFSET] = f'{self._CLASS_NAME}~'.encode('utf-8')
        self._lock.release()

    def _read_header(self):
        lock_acquired = self._lock.acquire(timeout=0.1)
        if not lock_acquired:
            warnings.warn(
                f'[{self._CLASS_NAME} - {self._name}] LOCKER TIMEOUT ERROR; Failed to interact with shared memory')
        identity_string = bytes(self._shared_memory.buf[:self._READ_OFFSET]).decode('utf-8').split('~')[0]
        self._lock.release()
        return identity_string

    def _read_lockbyte(self):
        byte_data = bytes(self._shared_memory.buf[self._READ_OFFSET:(self._READ_OFFSET + self._LOCK_OFFSET)])
        lock_status = byte_data.decode('utf-8')  # 'w' or 'r' or ' ' or '\x00'
        return lock_status

    def _write_lockbyte(self, lock_status):
        byte_data = lock_status.encode('utf-8')
        self._shared_memory.buf[self._READ_OFFSET:(self._READ_OFFSET + self._LOCK_OFFSET)] = byte_data

    def aquire_RWlock(self, operation, timeout=1000):
        if operation not in ['w', 'r']:
            raise ValueError(f'[{self._CLASS_NAME} - {self._name}] Invalid lock status')
        spin_count = 0
        lock_acquired = False
        while not lock_acquired and spin_count < timeout:
            lock_status = self._read_lockbyte()
            if lock_status in [' ', '\x00']:
                self._write_lockbyte(operation)
                lock_acquired = True
            elif lock_status == 'w':
                lock_acquired = False
            elif lock_status == 'r':
                if operation == 'w':
                    lock_acquired = False
                elif operation == 'r':
                    self._write_lockbyte(operation)
                    lock_acquired = True
            spin_count += 1
        if spin_count >= timeout:
            warnings.warn(f'[{self._CLASS_NAME} - {self._name}] TIMEOUT ERROR; Failed to acquire lock')
        return lock_acquired

    def release_RWlock(self):
        self._write_lockbyte(' ')

    @property
    def name(self):
        return self._name

    @property
    def size(self):
        return self._size

    def write(self, data):
        if not self.use_RWLock:
            lock_acquired = self._lock.acquire(timeout=0.1)
        else:
            lock_acquired = self.aquire_RWlock('w', timeout=1000)

        if lock_acquired:
            self._shared_memory.buf[(self._READ_OFFSET + self._LOCK_OFFSET):] = b'\x00' * self._size
            if data is not None:
                byte_data = json.dumps(data).encode('utf-8')
                self._shared_memory.buf[(self._READ_OFFSET + self._LOCK_OFFSET):(self._READ_OFFSET + self._LOCK_OFFSET + len(byte_data))] = byte_data

            if not self.use_RWLock:
                self._lock.release()
            else:
                self.release_RWlock()
        else:
            warnings.warn(f'[{self._CLASS_NAME} - {self._name}] TIMEOUT ERROR; Failed to write data from shared memory')


    def read(self):
        data = None
        if not self.use_RWLock:
            lock_acquired = self._lock.acquire(timeout=0.1)
        else:
            lock_acquired = self.aquire_RWlock('r', timeout=1000)

        if lock_acquired:
            try:
                byte_data = bytes(self._shared_memory.buf[(self._READ_OFFSET + self._LOCK_OFFSET):])
                _decoded_data = byte_data.decode('utf-8').split('\x00')[0]
                if _decoded_data:
                    try:
                        data = json.loads(_decoded_data)
                    except:
                        pass
            except Exception:
                warnings.warn(f'[{self._CLASS_NAME} - {self._name}] Failed to read data from shared memory')

            if not self.use_RWLock:
                self._lock.release()
            else:
                self.release_RWlock()
        else:
            warnings.warn(f'[{self._CLASS_NAME} - {self._name}] TIMEOUT ERROR; Failed to read data from shared memory')
            return data

        return data

    def clear(self):
        self.write(None)

    def close(self):
        self._shared_memory.close()

    def terminate(self):
        self.clear()
        self.close()
        self._shared_memory.unlink()

    def is_alive(self):
        try:
            tmp_buffer = shared_memory.SharedMemory(self._name)
            tmp_buffer.close()
            return True
        except FileNotFoundError:
            return False


class SharedNdarray:
    _CLASS_NAME = 'SharedNdarray'
    _MAX_BUFFER_SIZE = 2 ** 32  # Maximum shared memory: 4 GB
    _READ_OFFSET = 512  # The first 512 bytes represents the valid size of the shared buffer

    def __init__(self, name, lock: Lock, data=None, create=True):

        self._name = name
        self._lock = lock
        self._shared_memory = None
        self._dtype = None
        self._data = None

        if create:
            if data is None:
                raise ValueError(
                    f'[{self._CLASS_NAME} - {self._name}] Shared ndarray cannot be created: Data cannot be None')
            self._shape = data.shape
            self._dtype = data.dtype.str
            try:
                self._shared_memory = shared_memory.SharedMemory(create=True, name=self._name,
                                                                 size=data.nbytes + self._READ_OFFSET)
                self._write_header()
                self._data = np.ndarray(shape=self._shape, dtype=self._dtype, buffer=self._shared_memory.buf,
                                        offset=self._READ_OFFSET)
                self.write(data)
            except Exception:
                if self._shared_memory is not None:
                    self._shared_memory.close()
                    self._shared_memory.unlink()
                raise Exception(f'[{self._CLASS_NAME} - {self._name}] Error in writing data: {traceback.format_exc()}')
        else:
            self._shared_memory = shared_memory.SharedMemory(name=self._name)
            try:
                self._read_header()
            except Exception:
                print(traceback.format_exc())
                self.close()
                raise TypeError(f'[{self._CLASS_NAME} - {self._name}] Unsupported type of shared memory')

            self._data = np.ndarray(shape=self._shape, dtype=self._dtype, buffer=self._shared_memory.buf,
                                    offset=self._READ_OFFSET)
            if data is not None:
                try:
                    self.write(data)
                except Exception:
                    self.close()
                    raise Exception(
                        f'[{self._CLASS_NAME} - {self._name}] Error in writing data: {traceback.format_exc()}')

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    @property
    def name(self):
        return self._name

    @property
    def shape(self):
        return self._shape

    @property
    def size(self):
        return self._size

    def read(self):
        self._lock.acquire()
        data = self._data.copy()
        self._lock.release()
        return data

    def write(self, data):
        self._lock.acquire()
        self._data[:] = data
        self._lock.release()

    def _write_header(self):
        header = json.dumps(f'{self._CLASS_NAME}~{self._shape}~{self._dtype}').encode('utf-8')
        place_holder = ' ' * (self._READ_OFFSET - len(header))

        self._lock.acquire()
        self._shared_memory.buf[:self._READ_OFFSET] = header + place_holder.encode('utf-8')
        self._lock.release()

    def _read_header(self):
        self._lock.acquire()
        _decoded_header = bytes(self._shared_memory.buf[:self._READ_OFFSET]).decode('utf-8').split('\x00')[0]
        self._lock.release()

        identity_string = json.loads(_decoded_header).split('~')
        if identity_string[0] != self._CLASS_NAME:
            raise TypeError(f'[{self._CLASS_NAME} - {self._name}] Unsupported type of shared memory')
        else:
            self._shape = tuple([int(x) for x in identity_string[1][1:-1].split(',') if x])
            self._dtype = identity_string[-1]
            bytesize = np.dtype(self._dtype).itemsize
            self._size = np.prod(self._shape) * bytesize

    def close(self):
        self._shared_memory.close()

    def terminate(self):
        # self._shared_memory.close()
        self._shared_memory.unlink()
        if self.is_alive():
            warnings.warn(f"An unknown error occurred that caused the SharedBuffer {self.name} cannot be destroyed.")

    def is_alive(self):
        try:
            tmp_buffer = shared_memory.SharedMemory(name=self._name, create=False)
            is_alive = True
        except FileNotFoundError:
            is_alive = False
        try:
            tmp_buffer.close()
        except:
            pass
        return is_alive


class SharedDict(dict):
    _BUFFER_PREFIX = 'b*'

    def __init__(self, linked_memory_name: str, lock, *args, create=False, use_RWLock=True, size=2 ** 14, **kwargs):
        super().__init__(*args, **kwargs)
        self._init_param = {"name": linked_memory_name,
                            "lock": lock,
                            "data": dict(self),
                            "create": create,
                            "use_RWLock": use_RWLock,
                            "size": size}
        # self._linked_SharedBuffer = SharedBuffer(**self._init_param)
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
        # self._refresh()
        return super().__repr__()

    def __delitem__(self, key):
        if self._BUFFER_PREFIX in key.lower():
            raise Exception(f'The item [{key}] cannot be modified/deleted as it is linked with a buffer.')
        super().__delitem__(key)
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
        data = None
        timeout = 10
        counter = 0
        while data is None and counter < timeout:
            data = self._linked_SharedBuffer.read()
            counter += 1
        if data is not None:
            try:
                self._update(data)
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
