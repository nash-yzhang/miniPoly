import json
import traceback
import warnings
from multiprocessing import shared_memory, Lock

class SimpleBuffer:
    _CLASS_NAME = 'SimpleBuffer'
    _MAX_BUFFER_SIZE = 2 ** 24  # Maximum shared memory: 16 MB
    _READ_OFFSET = len(_CLASS_NAME) + 1  # The first 30 bytes represents the valid size of the shared buffer

    def __init__(self, name, lock, data=None, size=None, create=True):
        self._size = None
        self._name = name
        self._lock = lock

        byte_data = None

        if create:
            if size is None:
                if data is None:
                    raise ValueError("'size' must be a positive number different from zero")
                else:
                    byte_data = json.dumps(data).encode('utf-8')
                    nbytes_data = len(byte_data)
                    size = min(nbytes_data * 2 + self._READ_OFFSET, self._MAX_BUFFER_SIZE)
            else:
                if data is not None:
                    byte_data = json.dumps(data).encode('utf-8')
                    nbytes_data = len(byte_data)
                    if size < nbytes_data:
                        raise ValueError(
                            f'[{self._CLASS_NAME} - {self._name}] Input memory size ({size}) is smaller than the '
                            f'actual data size ({nbytes_data}).')

            self._size = size + 0
            size += self._READ_OFFSET

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
            self._size = self._shared_memory.size - self._READ_OFFSET
            try:
                identity_string = self._read_header()
                if identity_string != self._CLASS_NAME:
                    raise TypeError(f'[{self._CLASS_NAME} - {self._name}] Unsupported type of shared memory')
            except Exception:
                print(traceback.format_exc())
                self.close()
                raise TypeError(f'[{self._CLASS_NAME} - {self._name}] Unsupported type of shared memory')
            if data is not None:
                self.write(data)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def _write_header(self):
        self._lock.acquire()
        self._shared_memory.buf[:self._READ_OFFSET] = f'{self._CLASS_NAME}~'.encode('utf-8')
        self._lock.release()

    def _read_header(self):
        self._lock.acquire()
        identity_string = bytes(self._shared_memory.buf[:self._READ_OFFSET]).decode('utf-8').split('~')[0]
        self._lock.release()
        return identity_string

    @property
    def name(self):
        return self._name

    @property
    def size(self):
        return self._size

    def write(self, data):
        self.clear()
        self._lock.acquire()
        byte_data = json.dumps(data).encode('utf-8')
        self._shared_memory.buf[self._READ_OFFSET:(self._READ_OFFSET + len(byte_data))] = byte_data
        self._lock.release()

    def read(self):
        self._lock.acquire()
        byte_data = bytes(self._shared_memory.buf[self._READ_OFFSET:])
        _decoded_data = byte_data.decode('utf-8').splite('\x00')[0]
        if _decoded_data:
            data = json.loads(_decoded_data)
        else:
            data = None
        self._lock.release()
        return data

    def clear(self):
        self._lock.acquire()
        self._shared_memory.buf[self._READ_OFFSET:] = b'\x00' * self._size
        self._lock.release()

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
