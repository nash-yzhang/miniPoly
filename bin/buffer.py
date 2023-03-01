import json
import traceback
import warnings
from multiprocessing import shared_memory, Lock

import numpy as np


class SharedBuffer:
    '''
    Wrapper for multiprocessing.shared_memory
    '''
    _CLASS_NAME = 'SharedBuffer'
    _MAX_BUFFER_SIZE = 2 ** 32  # Maximum shared memory: 4 GB
    _READ_OFFSET = 30  # The first 30 bytes represents the valid size of the shared buffer

    def __init__(self, name, lock: Lock, data=None, size=None, create=True, force_write=False):
        self._size = None
        self._name = name
        self._lock = lock
        self._valid_size = 0  # The actual size with data loaded
        # self._lock = 0  # Non-negative integer

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
                    self.valid_size = nbytes_data
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
                identity_string = self._read(-self._READ_OFFSET, self._READ_OFFSET).split('~')
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
        :return:
        list: a list of the occurrence positions
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
        # identity_string = self._read(-self._READ_OFFSET, self._READ_OFFSET).split('~')
        identity_string = bytes(self._shared_memory.buf[:self._READ_OFFSET]).decode('utf-8')
        try:
            identity_string = json.loads(identity_string).split('~')
        except:
            raise TypeError(f'[{self._CLASS_NAME} - {self._name}] Unknown error in reading header')
        if identity_string[0] != self._CLASS_NAME:
            raise TypeError(f'[{self._CLASS_NAME} - {self._name}] Unsupported type of shared memory')
        else:
            self._valid_size = int(identity_string[-1])
        return self._valid_size

    @valid_size.setter
    def valid_size(self, val):
        self._lock.acquire()
        self._valid_size = val
        s_val = str(val)
        place_holder = '~' * (self._READ_OFFSET - len(self._CLASS_NAME + s_val) - 2)
        data = self._CLASS_NAME + place_holder + s_val
        byte_data = json.dumps(data).encode('utf-8')
        self._shared_memory.buf[:self._READ_OFFSET] = byte_data
        self._lock.release()

    @property
    def free_space(self):
        return self.size - self.valid_size

    def read(self):
        return self._read(0, self.valid_size)

    def _read(self, offset, length, mode='obj'):
    # def _read(self, offset, length, mode='obj', sudo=False):
        # if sudo:
        #     lock_gained = True
        # else:
        #     lock_gained = self.request_lock()
        # if lock_gained:
        offset += self._READ_OFFSET
        length += 0  # copy the data

        self._lock.acquire()
        _decoded_bytes = bytes(self._shared_memory.buf[offset:(offset + length)])
        if mode == 'obj':
            _decoded_bytes = _decoded_bytes.decode('utf-8').split('\x00')[0]
            if _decoded_bytes:
                try:
                    decoded = json.loads(_decoded_bytes)
                except:
                    raise ValueError(f'[{self._CLASS_NAME} - {self._name}] Cannot decode the data')
                self._lock.release()
                # if not sudo:
                #     self._mem_release()
                return decoded
            else:
                self._lock.release()
                # if not sudo:
                #     self._mem_release()
                return _decoded_bytes
        elif mode == 'bytes':
            self._lock.release()
            # if not sudo:
            #     self._mem_release()
            return _decoded_bytes
        else:
            self._lock.release()
            # if not sudo:
            #     self._mem_release()
            raise ValueError(f'[{self._CLASS_NAME} - {self._name}] Undefined reading mode {mode}')
        # else:
        #     raise TimeoutError(f'[{self._CLASS_NAME} - {self._name}]: Cannot get the read lock')

    def read_bytes(self):
        return self._read(0, self.valid_size, mode='bytes')

    def write(self, data, mode='overwrite', offset=0):
        '''
        :param data: picklable data
        :param mode: If 'overwrite' (default), the input offset will be ignored.
                     All contents in the existing memory will be overwritten by the input data;
                     If 'modify', the bytes in [offset:nbytes(data)] will be changed by data

        :param offset: Only for mode == 'modify'. The start position in the buffer for the set operation
        '''
        byte_data = json.dumps(data).encode('utf-8')
        if mode == 'overwrite':
            self.clean()
            self._set(byte_data, offset=0)
        elif mode == 'modify':
            self._set(byte_data, offset=offset)


    def clean(self):
        # self._set(b'\x00' * (self._size - offset), offset=offset)  # delete everything after offset
        self._lock.acquire()
        self._shared_memory.buf[:] = b'\x00' * self._size
        self._lock.release()
        self.valid_size = 0

    # def _mem_lock(self):
    #     if self.valid_size > -1:
    #         self._lock = self._valid_size * 1  # Make sure the value is copied
    #         self.valid_size = -1
    #
    # def _mem_release(self):
    #     self.valid_size = self._lock * 1  # Make sure the value is copied
    #     self._lock = 0
    #
    # def request_lock(self, timeout: int = 10000):
    #     itt = 0
    #     while itt < timeout:
    #         self._mem_lock()
    #         itt += 1
    #         if self._lock > -1:
    #             break
    #
    #     return self._lock > -1

    def _set(self, byte_data, offset):
        self._lock.acquire()
        if offset > max(self._valid_size - 1, 0):
            self._lock.release()
            # self._mem_release()
            raise IndexError(
                f'[{self._CLASS_NAME} - {self._name}] Offset ({offset}) out of range: ({self._valid_size - 1})')  # To make sure all binary contents are continuous and no gap (b'\x00') in between

        if (offset + len(byte_data)) > self._size:
            self._lock.release()
            # self._mem_release()
            raise ValueError(
                f'[{self._CLASS_NAME} - {self._name}] Data byte end position out of range (Offset: {offset}, Length: {len(byte_data)}). \nCheck if the data size is smaller than the buffer size')
        else:
            length = len(byte_data)

        offset += self._READ_OFFSET  # Protect the identity and size info block

        self._shared_memory.buf[offset:(offset + length)] = byte_data
        self._lock.release()
        self.valid_size = offset + length

        # if offset + length > self._lock:
        #     self._lock = offset + length

        # self._mem_release()
        # else:
        #     raise TimeoutError(f'[{self._CLASS_NAME} - {self._name}]: Cannot get the write lock')

    def close(self):
        try:
            self._shared_memory.close()
        except:
            pass

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
            tmp_buffer = SharedBuffer(self.name, lock=self._lock,create=False)
            tmp_buffer.close()
            return True
        except FileNotFoundError:
            return False

class SharedNdarray:

    _CLASS_NAME = 'SharedNdarray'
    _MAX_BUFFER_SIZE = 2 ** 32  # Maximum shared memory: 4 GB
    _READ_OFFSET = 128  # The first 128 bytes represents the valid size of the shared buffer
    def __init__(self, name, lock: Lock, data=None):

        self._name = name
        self._lock = lock

        if not self.is_alive():
            if data is None:
                raise ValueError(f'[{self._CLASS_NAME} - {self._name}] Shared ndarray cannot be created: Data cannot be None')
            self._shape = data.shape
            self._size = data.nbytes + self._READ_OFFSET
            try:
                self._shared_memory = shared_memory.SharedMemory(create=True, name=self._name, size=self._size)
                header = json.dumps(f'{self._CLASS_NAME}~{self._shape}~{self._size}').encode('utf-8')
                place_holder = ' ' * (self._READ_OFFSET - len(header))
                self._shared_memory.buf[:self._READ_OFFSET] = header+place_holder.encode('utf-8')
                self.write(data)
            except Exception:
                self.close()
                raise Exception(f'[{self._CLASS_NAME} - {self._name}] Error in writing data: {traceback.format_exc()}')
        else:
            self._shared_memory = shared_memory.SharedMemory(name=self._name)
            try:
                identity_string = self._read_buffer_header().split('~')
                if identity_string[0] != self._CLASS_NAME:
                    raise TypeError(f'[{self._CLASS_NAME} - {self._name}] Unsupported type of shared memory')
                else:
                    self._size = int(identity_string[2])
                    self._shape = tuple([int(x) for x in identity_string[1][1:-1].split(',')])
            except Exception:
                print(traceback.format_exc())
                self.close()
                raise TypeError(f'[{self._CLASS_NAME} - {self._name}] Unsupported type of shared memory')

            if data is not None:
                try:
                    self.write(data)
                except Exception:
                    self.close()
                    raise Exception(f'[{self._CLASS_NAME} - {self._name}] Error in writing data: {traceback.format_exc()}')

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
        data = np.frombuffer(self._shared_memory.buf, dtype=np.uint8,\
                             count=self._size-self._READ_OFFSET, offset=self._READ_OFFSET)+0 # Copy the data
        data = data.reshape(self._shape)
        self._lock.release()
        return data

    def write(self, data):
        self._lock.acquire()
        self._shared_memory.buf[self._READ_OFFSET:self._size] = data.tobytes()
        self._lock.release()

    def _read_buffer_header(self):
        self._lock.acquire()
        _decoded_header = bytes(self._shared_memory.buf[:self._READ_OFFSET]).decode('utf-8').split('\x00')[0]
        self._lock.release()
        return json.loads(_decoded_header)

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
            tmp_buffer.close()
            return True
        except FileNotFoundError:
            return False

class SharedDict(dict):
    _BUFFER_PREFIX = 'b*'

    def __init__(self, linked_memory_name: str, lock, *args, create=False, force_write=False, size=2 ** 14, **kwargs):
        super().__init__(*args, **kwargs)
        self._init_param = {"name": linked_memory_name,
                            "lock": lock,
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

