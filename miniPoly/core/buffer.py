import atomics as _atomics
import json
import numpy as np
import traceback
import warnings
from multiprocessing import shared_memory, Lock
from time import sleep

#: Lock-byte values for the write-lock CAS (item 15), as ints rather than the `bytes`
#: literals ('w'/' ') the rest of this module reads and writes. `atomics.BYTES` (1-byte
#: width) reports a correct result on the first `cmpxchg` call and then reports success
#: unconditionally on every later call regardless of the actual byte -- reproduced in
#: isolation on this platform, unrelated to contention. `atomics.UINT` on the identical
#: 1-byte buffer slice does not have this fault and was verified over repeated calls with
#: the byte forced back to a mismatching value before each one. The on-disk byte is
#: unchanged -- still literally 'w'/'r'/' '/'\x00' -- only the CAS's own view of it differs.
_LOCKBYTE_FREE = ord(' ')
_LOCKBYTE_WRITER = ord('w')


def _numpy_scalar_to_builtin(obj):
    """`default` hook for the JSON encoder: a numpy scalar becomes its Python type.

    Closes B1's realistic trigger. `np.float64` subclasses Python `float`, so stdlib
    json accepted it by accident, while **every other numpy scalar dtype raised** --
    inside `SharedBuffer.write`, for a value the caller had every reason to think was a
    number. Every OMS and motor state is numpy-derived, so a `dtype=` change upstream
    was enough to make a state stop updating.

    `.item()` yields `int`/`float`/`bool`, which is what
    `dockableGUI._update_surveillance_state_list` needs: it dispatches on
    `val_type in [int, float, bool]`, so a codec that preserved numpy types instead
    (pickle does) would silently drop those states from the live plots.

    Deliberately *not* `orjson`, which the roadmap had nominated for this job. It fixes
    the same eight dtypes and encodes ~7x faster, but it maps NaN and +-Infinity to
    `null`, i.e. to `None` on the way back. That is reachable here -- OMS derives its
    rotation states through `np.nanmean`, which returns NaN for an all-NaN window -- and
    `dockableGUI.rotate_sphere` calls `np.isnan(r)` on one of them, which raises
    TypeError for None. The encode saving was ~8 us on a SERVO tick, 0.8 % of its 1 ms
    budget, against a silent numeric conversion and a crash path. See roadmap item 11.
    """
    if isinstance(obj, np.generic):
        return obj.item()
    raise TypeError(f'Object of type {type(obj).__name__} is not JSON serializable')


#: One encoder, constructed once and reused. Passing `default=` to `json.dumps` builds a
#: fresh `JSONEncoder` on every call, which measured slower than plain `json.dumps` --
#: the hook is meant to cost nothing until it is needed. Output is byte-identical to
#: `json.dumps(data)` for everything json could already encode.
_ENCODER = json.JSONEncoder(default=_numpy_scalar_to_builtin)


def _encode(data):
    """Encode a payload for a shared segment. See `_numpy_scalar_to_builtin`."""
    return _ENCODER.encode(data).encode('utf-8')


class SharedBuffer:
    """
    The SharedBuffer class allows for the sharing of data with dynamic size and structure between processes.
    It utilizes the multiprocessing.shared_memory.SharedMemory module. This class is ideal for creating a shared
    data index where all data of a process and their addresses are listed. It's not optimized for high-speed or
    high-frequency data transfers.

    Used as the backend data structure of the SharedDict class .

    Segment layout::

        [0 : _READ_OFFSET)          identity string, 'SharedBuffer~'
        [_LENGTH_START - 1)         lock byte: 'w', 'r', ' ' or '\\x00'
        [_LENGTH_START, _DATA_OFFSET)  payload length, _LENGTH_OFFSET bytes, little-endian
        [_DATA_OFFSET : )              payload, exactly `length` bytes of it valid

    The payload length is stored explicitly rather than delimited by a NUL
    terminator. The terminator scheme cost 78 us of an 85 us read on an 8 KB
    segment, because recovering the payload meant decoding the *whole* region and
    splitting it -- a NUL-padded 8 KB segment splits into ~8000 string objects,
    almost all of them empty. With the length known, `read` slices exactly the
    valid bytes and the cost stops scaling with the segment size. It also removes
    the constraint that the encoding may not contain a NUL byte, which no longer
    rules out a binary codec.
    """

    _CLASS_NAME = 'SharedBuffer'
    _MAX_BUFFER_SIZE = 2 ** 24  # Maximum shared memory: 16 MB
    _READ_OFFSET = len(_CLASS_NAME) + 1  # The identity string occupies the first bytes
    _LOCK_OFFSET = 1  # The next byte represents the lock status of the shared buffer
    _LENGTH_OFFSET = 4  # The next 4 bytes hold the payload length; 4 covers _MAX_BUFFER_SIZE
    _LENGTH_START = _READ_OFFSET + _LOCK_OFFSET
    _DATA_OFFSET = _READ_OFFSET + _LOCK_OFFSET + _LENGTH_OFFSET  # The payload starts here

    def __init__(self, name, lock, use_RWLock=False, data=None, size=None, create=True):
        """
        Initializes the SharedBuffer object.

        Parameters:
            name (str): The name of the shared memory segment.
            lock (multiprocessing.Lock): A lock object to ensure thread-safe operations.
            use_RWLock (bool): If set to True, it enables the use of read-write lock mechanism.
            data (any, optional): Initial data to write into the shared memory.
            size (int, optional): The size of the shared memory. If not specified, it's calculated based on the data.
            create (bool): If True, a new shared memory segment is created. Otherwise, an existing segment is used.

        Raises:
            ValueError: If required parameters are missing or incorrect.
        """

        self._size = None
        self._name = name
        self._lock = lock
        self._use_RWLock = use_RWLock
        self._lockbyte_ctx = None
        self._lockbyte_view = None

        byte_data = None

        if create:
            if size is None:
                if data is None:
                    raise ValueError("'size' must be a positive number different from zero")
                else:
                    byte_data = _encode(data)
                    nbytes_data = len(byte_data)
                    size = min(nbytes_data * 2 + self._DATA_OFFSET, self._MAX_BUFFER_SIZE)
            else:
                if data is not None:
                    byte_data = _encode(data)
                    nbytes_data = len(byte_data)
                    if size < nbytes_data:
                        raise ValueError(
                            f'[{self._CLASS_NAME} - {self._name}] Input memory size ({size}) is smaller than the '
                            f'actual data size ({nbytes_data}).')

            self._size = size + 0
            size += self._DATA_OFFSET

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
            self._size = self._shared_memory.size - self._DATA_OFFSET
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
        """Context-manager entry; returns self unchanged."""
        return self

    def __exit__(self, *args):
        """Context-manager exit: closes the handle regardless of how the block exited."""
        self.close()

    def _write_header(self):
        """
        Writes the header information to the shared memory. This includes the class name and initial settings.
        It's a private method, used internally during initialization and write operations.

        Blocks until `self._lock` is acquired rather than giving up after 0.1 s (matching
        `SharedNdarray._write_header`). A segment this method is still writing to has no
        other legitimate holder of the lock yet, so contention here can only come from
        unrelated segments sharing the same lock object -- brief by construction. Giving
        up used to leave the identity string unwritten (breaking every future attach) and
        the lock byte at the OS's zero-fill '\\x00' instead of the ' ' the write-lock CAS
        (item 15) requires as its one free value, silently wedging that segment's write
        lock for good.
        """

        lock_acquired = self._lock.acquire()
        if not lock_acquired:
            warnings.warn(f'[{self._CLASS_NAME} - {self._name}] LOCK ERROR; Failed to interact with shared memory')
            return
        self._shared_memory.buf[:self._READ_OFFSET] = f'{self._CLASS_NAME}~'.encode('utf-8')
        # Explicit ' ' rather than the OS's zero-fill ('\x00'), so the write-lock's atomic
        # CAS (aquire_RWlock, item 15) has exactly one "free" value to compare against
        # instead of two. Both were already treated as equivalent everywhere that reads
        # the byte, so this changes no observable behaviour on the read side.
        self._shared_memory.buf[self._READ_OFFSET:self._LENGTH_START] = b' '
        self._lock.release()

    def _read_header(self):
        """
        Reads the header information from the shared memory. This is used to verify the type of shared memory being interacted with.
        It's a private method.
        """

        lock_acquired = self._lock.acquire(timeout=0.1)
        if not lock_acquired:
            warnings.warn(
                f'[{self._CLASS_NAME} - {self._name}] LOCKER TIMEOUT ERROR; Failed to interact with shared memory')
            return None
        identity_string = bytes(self._shared_memory.buf[:self._READ_OFFSET]).decode('utf-8').split('~')[0]
        self._lock.release()
        return identity_string

    def _read_lockbyte(self):
        """Raw, unsynchronized read of the lock byte.

        Used on the reader side of `aquire_RWlock`'s spin loop, where an unsynchronized
        snapshot is the point -- the loop re-reads until it likes what it sees. Not a
        substitute for the atomic CAS the writer side uses instead.
        """
        # private method for reading the lock status of the shared memory in the buffer header (self._READ_OFFSET)

        byte_data = bytes(self._shared_memory.buf[self._READ_OFFSET:(self._READ_OFFSET + self._LOCK_OFFSET)])
        lock_status = byte_data.decode('utf-8')  # 'w' or 'r' or ' ' or '\x00'
        return lock_status

    def _write_lockbyte(self, lock_status):
        """Raw, unsynchronized write of the lock byte.

        Used to both set it (the reader-acquire path, `_write_header`) and clear it
        (`release_RWlock`). The writer-acquire path deliberately does not use this --
        see `aquire_RWlock` for why it needs the atomic CAS instead.
        """
        # private method for updating buffer header (self._READ_OFFSET)

        byte_data = lock_status.encode('utf-8')
        self._shared_memory.buf[self._READ_OFFSET:(self._READ_OFFSET + self._LOCK_OFFSET)] = byte_data

    def _read_length(self):
        """Raw read of the payload-length field.

        Meaningful only while the caller already holds the read or write lock -- `read`
        is the only caller, and calls it from inside its own locked section.
        """
        # private method for reading how many payload bytes are valid (self._LENGTH_START)

        return int.from_bytes(bytes(self._shared_memory.buf[self._LENGTH_START:self._DATA_OFFSET]), 'little')

    def _write_length(self, nbytes):
        """Raw write of the payload-length field.

        Called by `write` only after the payload bytes are already in place and only
        while holding the write lock -- see `write` for why that ordering (payload
        before length) matters to a reader that gets in mid-write.
        """
        # private method for recording how many payload bytes are valid (self._LENGTH_START)

        self._shared_memory.buf[self._LENGTH_START:self._DATA_OFFSET] = \
            nbytes.to_bytes(self._LENGTH_OFFSET, 'little')

    def aquire_RWlock(self, operation, timeout=1000):

        """
        Acquires the read-write lock for either reading or writing operations.

        Parameters:
            operation (str): 'w' for write, 'r' for read.
            timeout (int): The maximum time to wait for acquiring the lock.

        Returns:
            bool: True if the lock is acquired, False otherwise.

        Raises:
            ValueError: If an invalid operation is specified.
        """

        if operation not in ['w', 'r']:
            raise ValueError(f'[{self._CLASS_NAME} - {self._name}] Invalid lock status')
        spin_count = 0
        lock_acquired = False
        if operation == 'w':
            # Atomic compare-and-swap (item 15): the old read-then-write let two writers
            # both observe 'free' and both proceed (defect: lock-byte-test-and-set-is-not-
            # atomic, measured losing 34% of increments under real contention). The reader
            # path below is deliberately untouched -- an atomic op here would run on every
            # foreign read, which 2.2's budget note rules out.
            view = self._lockbyte_atomicview()
            while not lock_acquired and spin_count < timeout:
                lock_acquired = view.cmpxchg_weak(expected=_LOCKBYTE_FREE, desired=_LOCKBYTE_WRITER).success
                spin_count += 1
        else:
            while not lock_acquired and spin_count < timeout:
                lock_status = self._read_lockbyte()
                if lock_status in [' ', '\x00']:
                    self._write_lockbyte(operation)
                    lock_acquired = True
                elif lock_status == 'w':
                    lock_acquired = False
                elif lock_status == 'r':
                    self._write_lockbyte(operation)
                    lock_acquired = True
                spin_count += 1
        if spin_count >= timeout:
            warnings.warn(f'[{self._CLASS_NAME} - {self._name}] TIMEOUT ERROR; Failed to acquire lock')
        return lock_acquired

    def _lockbyte_atomicview(self):
        """The write-lock byte's atomic view, opened once and held (item 15).

        Opening `atomicview` measured ~4x the cost of an already-open operation, so like
        `BaseMinion`'s heartbeat view, this is created on first use and kept for the
        object's life rather than reopened per acquire.
        """
        if self._lockbyte_view is None:
            self._lockbyte_ctx = _atomics.atomicview(
                buffer=self._shared_memory.buf[self._READ_OFFSET:self._LENGTH_START], atype=_atomics.UINT)
            self._lockbyte_view = self._lockbyte_ctx.__enter__()
        return self._lockbyte_view

    def release_RWlock(self):
        """
        Releases the read-write lock. Should be called after completing a read or write operation.
        """

        self._write_lockbyte(' ')

    @property
    def name(self):
        """
        Returns:
            str: The name of the shared memory segment. Useful for identifying the shared buffer.
        """
        return self._name

    @property
    def size(self):
        """
        Returns:
            int: The size of the data area in the shared memory segment (excluding header and lock areas).
        """
        return self._size

    def write(self, data):
        """
        Writes data to the shared memory.

        Encoding and the size check both happen *before* the lock is taken and before
        the data region is touched, and the lock is released in a `finally`. A write
        that cannot complete therefore leaves the previous payload readable and the
        lock byte free. Previously the region was zero-filled first and the lock was
        released only on the success path, so a raising encode wiped the payload and
        left the lock byte at 'w' for the remaining life of the segment -- silently
        making it unreadable and unwritable for every process holding a handle.

        The zero-fill is gone as well. It existed only to keep the NUL terminator
        scheme working, and it made every write -- including one holding a 20 byte
        payload -- pay for clearing the entire segment. Bytes past `length` are now
        simply stale and unreachable; `read` never looks at them.

        The length is written *after* the payload, so a reader that gets in mid-write
        (the test-and-set is still not atomic -- see `aquire_RWlock`) sees the old
        length rather than a length that outruns the bytes actually written. That is
        not a fix for the race, only a choice of which torn state is safer: a stale
        length can address a partly overwritten payload, which fails to decode and
        reads as None, and `SharedDict._refresh` retries.

        Parameters:
            data (any): The data to be written into the shared memory. It should be serializable.

        Raises:
            ValueError: If the encoded data does not fit the data region.
            TypeError: Propagated from the JSON encoder for a value it cannot represent
                (every numpy scalar dtype except float64, for instance).
            Warning: If there's a timeout or failure in acquiring the lock for writing.
        """

        # None is written as an empty region rather than as the literal 'null', which
        # is what read() reports back as None.
        byte_data = b'' if data is None else _encode(data)
        if len(byte_data) > self._size:
            raise ValueError(
                f'[{self._CLASS_NAME} - {self._name}] Encoded data ({len(byte_data)} bytes) does not fit '
                f'the data region ({self._size} bytes).')

        if not self._use_RWLock:
            lock_acquired = self._lock.acquire(timeout=0.1)
        else:
            lock_acquired = self.aquire_RWlock('w', timeout=1000)

        if not lock_acquired:
            warnings.warn(f'[{self._CLASS_NAME} - {self._name}] TIMEOUT ERROR; Failed to write data from shared memory')
            return

        try:
            if byte_data:
                self._shared_memory.buf[self._DATA_OFFSET:(self._DATA_OFFSET + len(byte_data))] = byte_data
            self._write_length(len(byte_data))
        finally:
            if not self._use_RWLock:
                self._lock.release()
            else:
                self.release_RWlock()

    def read(self):
        """
        Reads data from the shared memory.

        Slices exactly the bytes the last write declared valid. The payload is handed
        to `json.loads` as bytes -- it decodes UTF-8 itself -- so neither the decode
        nor the NUL split runs over the unused tail of the segment. On an 8 KB segment
        that took the read from 85 us to a few microseconds, and the cost no longer
        grows with the segment size.

        A length larger than the data region means the header is not one this class
        wrote (a foreign segment that passed the identity check, or a corrupted one);
        it is reported like any other read failure rather than raising on the slice.

        Returns:
            any: The data read from the shared memory, or None if no data is found or in case of a read error.

        Raises:
            Warning: If there's a timeout or failure in acquiring the lock for reading.
        """

        data = None
        if not self._use_RWLock:
            lock_acquired = self._lock.acquire(timeout=0.1)
        else:
            lock_acquired = self.aquire_RWlock('r', timeout=1000)

        if lock_acquired:
            try:
                nbytes = self._read_length()
                if nbytes > self._size:
                    raise ValueError(f'declared payload length ({nbytes}) exceeds the data region '
                                     f'({self._size} bytes)')
                if nbytes:
                    byte_data = bytes(self._shared_memory.buf[self._DATA_OFFSET:(self._DATA_OFFSET + nbytes)])
                    try:
                        data = json.loads(byte_data)
                    except:
                        pass
            except Exception:
                warnings.warn(f'[{self._CLASS_NAME} - {self._name}] Failed to read data from shared memory')

            if not self._use_RWLock:
                self._lock.release()
            else:
                self.release_RWlock()
        else:
            warnings.warn(f'[{self._CLASS_NAME} - {self._name}] TIMEOUT ERROR; Failed to read data from shared memory')
            return data

        return data

    def clear(self):
        """
        Clears the data in the shared memory. This is equivalent to writing None.

        It sets the payload length to zero rather than overwriting the bytes, so the
        previous payload is still physically present in the segment -- unreachable
        through `read`, but not scrubbed. The only caller that cared was `terminate`,
        which unlinks immediately afterwards.
        """

        self.write(None)

    def close(self):
        """
        Closes the shared memory segment. It should be called to free resources when the shared memory is no longer needed.
        """

        if self._lockbyte_view is not None:
            try:
                self._lockbyte_ctx.__exit__(None, None, None)
            except Exception:
                pass
            self._lockbyte_view = None
        self._shared_memory.close()

    def terminate(self):
        """
        Clears the shared memory and unlinks it. This should be used to completely remove the shared memory segment.
        """

        self.clear()
        self.close()
        self._shared_memory.unlink()

    def __del__(self):
        """Best-effort cleanup for a handle whose owner never called `close()`.

        See `_release_lockbyte_view` for why this is the normal path, not an edge case.
        """
        self._release_lockbyte_view()

    def _release_lockbyte_view(self):
        """Release the held-open `atomicview` without needing `close()` to be called.

        `atomics.AtomicViewContext.__del__` raises ValueError when the context is still
        open, which the interpreter reports as an ignored exception -- a traceback on
        every clean exit. The process that hits this is the **parent**: it constructs
        every minion, so `__init__`'s first write opens a view per segment here, and
        `_shutdown()` (the only caller of `close()`) runs in the child. So this is the
        normal path, not an edge case.
        """

        try:
            if getattr(self, '_lockbyte_view', None) is not None:
                self._lockbyte_ctx.__exit__(None, None, None)
                self._lockbyte_view = None
        except Exception:
            # __del__ during interpreter shutdown: modules may already be torn down, and
            # raising here would replace one ignored traceback with another.
            pass

    def is_alive(self):
        """
        Checks if the shared memory segment is still accessible.

        Returns:
            bool: True if the shared memory segment is accessible, False otherwise.
        """
        try:
            tmp_buffer = shared_memory.SharedMemory(self._name)
            tmp_buffer.close()
            return True
        except FileNotFoundError:
            return False


class SharedNdarray:
    """
    SharedNdarray allows efficient sharing of NumPy arrays between processes using shared memory. It is useful for large data
    sets where duplicating data for each process is not feasible due to memory constraints.
    """

    _CLASS_NAME = 'SharedNdarray'
    _MAX_BUFFER_SIZE = 2 ** 32  # Maximum shared memory: 4 GB
    _READ_OFFSET = 512  # The first 512 bytes represents the valid size of the shared buffer
    _LOCK_OFFSET = 1  # The next byte represents the lock status of the shared buffer

    def __init__(self, name, lock: Lock, data=None, create=True, use_RWLock=True):
        """
        Initializes a SharedNdarray object.

        Parameters:
            name (str): Unique identifier for the shared memory segment.
            lock (Lock): Synchronization primitive to ensure thread-safe operations.
            data (np.ndarray, optional): Initial array data to store in shared memory.
            create (bool): Flag to indicate whether to create a new shared memory segment.
            use_RWLock (bool): Flag to indicate the use of a read-write lock for thread safety.

        Raises:
            ValueError: If data is None when create is True.
        """

        self._name = name
        self._lock = lock
        self._use_RWLock = use_RWLock
        self._lockbyte_ctx = None
        self._lockbyte_view = None

        self._shared_memory = None
        self._dtype = None
        self._data = None

        if create:
            if data is None:
                raise ValueError(
                    f'[{self._CLASS_NAME} - {self._name}] Shared ndarray cannot be created: Data cannot be None')
            self._shape = data.shape
            self._dtype = data.dtype.str
            # Same quantity `_read_header` derives on the attach path, so `size` reads
            # the same on a creator as on anyone who attaches to the segment later.
            self._size = data.nbytes
            try:
                self._shared_memory = shared_memory.SharedMemory(create=True, name=self._name,
                                                                 size=data.nbytes + self._READ_OFFSET + self._LOCK_OFFSET)
                self._write_header()
                self._data = np.ndarray(shape=self._shape, dtype=self._dtype, buffer=self._shared_memory.buf,
                                        offset=self._READ_OFFSET + self._LOCK_OFFSET)
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
                                    offset=self._READ_OFFSET + self._LOCK_OFFSET)
            if data is not None:
                try:
                    self.write(data)
                except Exception:
                    self.close()
                    raise Exception(
                        f'[{self._CLASS_NAME} - {self._name}] Error in writing data: {traceback.format_exc()}')

    def __enter__(self):
        """Context-manager entry; returns self unchanged."""
        return self

    def __exit__(self, *args):
        """Context-manager exit: closes the handle regardless of how the block exited."""
        self.close()

    @property
    def name(self):
        """The shared-memory segment's name."""
        return self._name

    @property
    def shape(self):
        """The array's shape, as recorded by `_write_header`/decoded by `_read_header`."""
        return self._shape

    @property
    def size(self):
        """The payload size in bytes, excluding the header and lock byte.

        Set on both construction paths -- from `data.nbytes` when creating, and derived
        from shape and dtype by `_read_header` when attaching -- so it reads the same
        whichever end of the segment holds this handle.
        """
        return self._size

    def _read_lockbyte(self):
        """
        Private method: Reads the lock status byte from the shared memory.

        Returns:
            str: The current lock status ('w', 'r', ' ', '\x00').
        """

        byte_data = bytes(self._shared_memory.buf[self._READ_OFFSET:(self._READ_OFFSET + self._LOCK_OFFSET)])
        lock_status = byte_data.decode('utf-8')  # 'w' or 'r' or ' ' or '\x00'
        return lock_status

    def _write_lockbyte(self, lock_status):
        """
        Writes the lock status byte to the shared memory.

        Parameters:
            lock_status (str): The lock status to write ('w', 'r', ' ', '\x00').
        """
        byte_data = lock_status.encode('utf-8')
        self._shared_memory.buf[self._READ_OFFSET:(self._READ_OFFSET + self._LOCK_OFFSET)] = byte_data

    def aquire_RWlock(self, operation, timeout=1000):
        """Acquire the read or write lock on this segment; spins up to `timeout` tries.

        Mirrors `SharedBuffer.aquire_RWlock`: the writer side is an atomic
        compare-and-swap against the single "free" value (item 15), while the reader
        side is a plain read-then-write and stays racy by construction -- see that
        method's docstring for why the two paths differ. Returns False (with a warning)
        rather than raising when the spin budget runs out, so `write`/`read` must check
        the result before touching `_data`.
        """
        if operation not in ['w', 'r']:
            raise ValueError(f'[{self._CLASS_NAME} - {self._name}] Invalid lock status')
        spin_count = 0
        lock_acquired = False
        if operation == 'w':
            # Atomic CAS (item 15); see SharedBuffer.aquire_RWlock for why the reader
            # path below is left as-is.
            view = self._lockbyte_atomicview()
            while not lock_acquired and spin_count < timeout:
                lock_acquired = view.cmpxchg_weak(expected=_LOCKBYTE_FREE, desired=_LOCKBYTE_WRITER).success
                spin_count += 1
        else:
            while not lock_acquired and spin_count < timeout:
                lock_status = self._read_lockbyte()
                if lock_status in [' ', '\x00']:
                    self._write_lockbyte(operation)
                    lock_acquired = True
                elif lock_status == 'w':
                    lock_acquired = False
                elif lock_status == 'r':
                    self._write_lockbyte(operation)
                    lock_acquired = True
                spin_count += 1
        if spin_count >= timeout:
            warnings.warn(f'[{self._CLASS_NAME} - {self._name}] TIMEOUT ERROR; Failed to acquire lock')
        return lock_acquired

    def _lockbyte_atomicview(self):
        """The write-lock byte's atomic view, opened once and held (item 15)."""
        if self._lockbyte_view is None:
            self._lockbyte_ctx = _atomics.atomicview(
                buffer=self._shared_memory.buf[self._READ_OFFSET:(self._READ_OFFSET + self._LOCK_OFFSET)],
                atype=_atomics.UINT)
            self._lockbyte_view = self._lockbyte_ctx.__enter__()
        return self._lockbyte_view

    def release_RWlock(self):
        """Clear the lock byte to 'free'. Must be called after a successful acquire."""
        self._write_lockbyte(' ')

    def read(self):
        """Return a copy of the array, taken while holding the read (or instance) lock.

        Copies out of shared memory before releasing the lock, so the returned array
        stays valid even after a peer starts writing -- unlike `_data`, which aliases
        the shared buffer directly and would otherwise let the caller observe a
        concurrent write mid-flight. Returns None (with a warning) if the lock could
        not be acquired within the timeout.
        """
        if self._use_RWLock:
            lock_acquired = self.aquire_RWlock('r')
        else:
            lock_acquired = self._lock.acquire()

        if not lock_acquired:
            warnings.warn(f'[{self._CLASS_NAME} - {self._name}] TIMEOUT ERROR; Failed to read data from shared memory')
            return None
        else:
            data = self._data.copy()

            if self._use_RWLock:
                self.release_RWlock()
            else:
                self._lock.release()
        return data

    def write(self, data):
        """
        Writes an array into the shared segment.

        Takes the **write** lock. It used to take `'r'`, which let another writer and
        any reader in while a write was in progress, so a half-written frame was
        visible in the preview. Removing that direct race does not make the lock sound
        -- there is still no reader count and the test-and-set is still not atomic --
        it only stops `write()` from advertising itself as a reader.

        The assignment is wrapped in `finally` for the same reason as
        `SharedBuffer.write`: a shape or dtype mismatch raises inside the critical
        section, and without it the lock byte would stay at 'w' for the remaining life
        of the segment.
        """
        if self._use_RWLock:
            lock_acquired = self.aquire_RWlock('w')
        else:
            lock_acquired = self._lock.acquire()

        if not lock_acquired:
            warnings.warn(f'[{self._CLASS_NAME} - {self._name}] TIMEOUT ERROR; Failed to write data to shared memory')
            return None

        try:
            self._data[:] = data
        finally:
            if self._use_RWLock:
                self.release_RWlock()
            else:
                self._lock.release()

    def _write_header(self):
        """
        Writes the header information to the shared memory, including class name, shape, and dtype of the ndarray.
        """
        header = json.dumps(f'{self._CLASS_NAME}~{self._shape}~{self._dtype}').encode('utf-8')
        place_holder = ' ' * (self._READ_OFFSET - len(header))

        self._lock.acquire()
        self._shared_memory.buf[:self._READ_OFFSET] = header + place_holder.encode('utf-8')
        # Explicit ' ' rather than the OS's zero-fill ('\x00'): the write-lock's atomic
        # CAS (aquire_RWlock, item 15) needs exactly one "free" value to compare against.
        self._shared_memory.buf[self._READ_OFFSET:(self._READ_OFFSET + self._LOCK_OFFSET)] = b' '
        self._lock.release()

    def _read_header(self):
        """
        Reads the header information from the shared memory to determine the array's shape and dtype.
        """

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
        """
        Closes the shared memory segment and releases resources.
        """

        if self._lockbyte_view is not None:
            try:
                self._lockbyte_ctx.__exit__(None, None, None)
            except Exception:
                pass
            self._lockbyte_view = None
        self._shared_memory.close()

    def __del__(self):
        """Best-effort release of the held-open lock-byte atomic view."""
        # Same reason as SharedBuffer.__del__: the parent process opens a view per
        # segment and never calls close(), so without this every clean exit prints an
        # ignored ValueError from atomics' own __del__.
        try:
            if getattr(self, '_lockbyte_view', None) is not None:
                self._lockbyte_ctx.__exit__(None, None, None)
                self._lockbyte_view = None
        except Exception:
            pass

    def terminate(self):
        """
        Closes this handle and unlinks the shared memory segment.

        Close, unlink, done -- with **no wait for the segment to disappear**. The original
        retried `while self.is_alive() and timeout < 10` with a counter that was never
        incremented, so it was `while self.is_alive()`; on Windows `SharedMemory.unlink()`
        is a no-op and the segment lives until its last handle closes, so `is_alive()`
        stayed True for as long as any peer held a handle and the loop could never end.
        That was defect C9. It had stayed invisible because B3's KeyError aborted
        `_shutdown()` before it ever got here.

        Waiting is pointless, not merely slow: once this process has closed and unlinked,
        nothing it does can retire a segment another process still holds, and `shm_unlink`
        has no transient failure mode on POSIX either. A first attempt at this fix kept a
        bounded retry (10 x 100 ms) and so spent a **full second per buffer** on every
        shutdown, because a peer holding a handle is the normal case rather than the
        exceptional one -- caught by `check_status_poll_stays_responsive` in
        tests/test_failure_paths.py, which measured a 1030 ms reaction.

        A segment that outlives this call is therefore not an error. It means a peer is
        still attached, and the OS reclaims it when that peer closes.
        """

        try:
            self._shared_memory.close()
        except Exception:
            pass

        try:
            self._shared_memory.unlink()
        except FileNotFoundError:
            pass
        except Exception:
            warnings.warn(f"[{self._CLASS_NAME} - {self._name}] Failed to unlink the shared memory segment:\n"
                          f"{traceback.format_exc()}")

    def is_alive(self):
        """
        Checks if the shared memory segment is still accessible.

        Returns:
            bool: True if accessible, False otherwise.
        """

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
    """A dict whose contents live in a `SharedBuffer`, re-read on every access.

    Because the whole dict is one JSON blob, writing one key re-encodes and rewrites
    all of them. `defer_writes` exists for the caller that writes several keys in a
    burst -- a minion updating its states once per tick -- and turns that burst into a
    single encode and a single write. See `flush` for what the deferral does and does
    not change.
    """

    _BUFFER_PREFIX = 'b*'

    def __init__(self, linked_memory_name: str, lock, *args, create=False, use_RWLock=True, size=2 ** 14, **kwargs):
        """Create or attach to the backing `SharedBuffer` plus a paired generation-counter segment.

        `*args`/`**kwargs` seed the local dict via `dict.__init__` before the buffer is
        touched, so on `create=True` that seed data is exactly what gets published as
        the segment's initial contents (passed through as `data` to
        `SharedBuffer.__init__`). On `create=False` this instead attaches to two
        already-existing segments -- `linked_memory_name` and
        `linked_memory_name + "_generation"` -- created by whichever process passed
        `create=True` first; local seed data is pointless there since the attach path of
        `SharedBuffer.__init__` ignores `data`.

        `self._pending`/`self._defer_writes`/etc. are initialized before the
        `SharedBuffer` is constructed so that any codepath reachable during construction
        which lands in `__setitem__` or `_refresh` finds them already in place.
        """
        super().__init__(*args, **kwargs)
        # Before anything that can reach __setitem__ or _refresh.
        self._pending = {}
        self._defer_writes = False
        self._generation_ctx = None
        self._generation_view = None
        self._init_param = {"name": linked_memory_name,
                            "lock": lock,
                            "data": dict(self),
                            "create": create,
                            "use_RWLock": use_RWLock,
                            "size": size}
        # self._linked_SharedBuffer = SharedBuffer(**self._init_param)
        self._linked_SharedBuffer = SharedBuffer(**self._init_param)
        self.is_alive = True

        # A per-segment change counter (roadmap item 14), separate from the dict segment
        # so it needs no change to SharedBuffer's layout. Multi-writer: `set_foreign_state`
        # writes into a peer's dict from its own process at 39 sites in the application,
        # so every writer -- owner or foreign -- bumps the same counter atomically. Readers
        # compare "generation I last saw" against "generation now" instead of diffing a
        # value, which is what `watch_state`'s private per-reader copy does today; nothing
        # here migrates that caller yet (roadmap item 20).
        generation_name = f"{linked_memory_name}_generation"
        if create:
            self._generation_shm = shared_memory.SharedMemory(create=True, name=generation_name, size=4)
            self._generation_shm.buf[0:4] = (0).to_bytes(4, "little")
        else:
            self._generation_shm = shared_memory.SharedMemory(name=generation_name)

    def __setitem__(self, key, value):
        """Set a key, guarding buffer-linked keys and honoring `defer_writes`.

        A key already carrying a `b*`-prefixed buffer link cannot be reassigned through
        this path -- only `unlink` may remove it -- because overwriting it here would
        silently drop the link without releasing what it points to. The local dict is
        updated first in every case, so this process reads its own write back
        immediately; when deferring, the value is queued in `_pending` instead of
        reaching shared memory, to be picked up by the next `flush`. Otherwise it
        re-encodes and rewrites the *whole* dict (see class docstring) and bumps the
        generation counter. A write failure is caught and printed rather than raised, so
        one bad value cannot make an ordinary assignment statement raise.
        """
        if self._BUFFER_PREFIX in key.lower():
            if key in self.keys():
                raise Exception(f'The item [{key}] cannot be modified/deleted as it is linked with a buffer.')

        super().__setitem__(key, value)
        if self._defer_writes:
            # Local copy updated above, so this process reads its own value back
            # immediately; peers see it at the next flush.
            self._pending[key] = value
            return
        try:
            self._linked_SharedBuffer.write(dict(self))
            self._bump_generation()
        except Exception:
            print(traceback.format_exc())

    def __getitem__(self, key):
        """Refresh from shared memory, then return the local copy's value for `key`.

        Every read pays for a `_refresh()` (a `SharedBuffer.read` plus its retry loop),
        so this reflects the latest state any peer has flushed rather than a stale
        local copy -- at the cost of a shared-memory read on every single `d[key]`.
        """
        self._refresh()
        return super().__getitem__(key)

    def __repr__(self):
        """`dict.__repr__` of the local copy only -- deliberately does not refresh first."""
        # self._refresh()
        return super().__repr__()

    def __delitem__(self, key):
        """Delete a key and immediately push the resulting dict to shared memory.

        Buffer-linked (`b*`-prefixed) keys are rejected for the same reason as in
        `__setitem__`. Unlike `__setitem__`, this always writes through even when
        `defer_writes` is on -- a deletion is never queued in `_pending`.
        """
        if self._BUFFER_PREFIX in key.lower():
            raise Exception(f'The item [{key}] cannot be modified/deleted as it is linked with a buffer.')
        super().__delitem__(key)
        self._linked_SharedBuffer.write(dict(self))
        self._bump_generation()

    # def __del__(self):
    #     self.close()

    def __enter__(self):
        """Context-manager entry: refresh from shared memory, then return self."""
        self._refresh()
        return self

    def __exit__(self, *args):
        """Context-manager exit: closes the handle regardless of how the block exited."""
        self.close()

    def _refresh(self):
        """Pull the latest published state into the local dict, keeping deferred writes on top.

        Retries the underlying `SharedBuffer.read()` up to 10 times when it comes back
        None, since a reader can land mid-write and get a torn payload that fails to
        decode (see `SharedBuffer.write`'s note on writing length only after the
        payload). `_clear()` runs first so a key a peer removed since the last refresh
        actually disappears locally, instead of lingering from a previous `_update`.

        Any keys still in `self._pending` -- writes this process made but has not
        flushed yet -- are re-applied on top of what shared memory reported, because
        `_clear()` would otherwise make a deferred write invisible even to the process
        that made it, until it flushes.
        """
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
        # Unflushed writes go back on top of what shared memory says. `_clear()` above
        # drops them from the local copy otherwise, so without this a deferred write
        # would be invisible even to the process that made it, until it flushed.
        if self._pending:
            self._update(self._pending)

    def _update(self, D, **kwargs):
        """Thin wrapper over `dict.update`, giving callers one seam to route through."""
        super().update(D, **kwargs)

    def _clear(self):
        """Thin wrapper over `dict.clear`, giving callers one seam to route through."""
        super().clear()

    def defer_writes(self, enabled=True):
        """Collect `__setitem__` into one write per `flush` instead of writing each one.

        Off by default: a bare `SharedDict` behaves exactly as it always did. Minions
        turn it on for their own state dict in `prepare_shared_buffer`, where the write
        burst is a tick's worth of `set_state` calls.

        Turning it off flushes first, so no write is silently dropped.
        """
        if not enabled:
            self.flush()
        self._defer_writes = enabled

    def flush(self):
        """Write every deferred key in one encode. Returns True if anything was written.

        `_refresh()` first, deliberately: the segment is a single blob, so writing it
        means writing every key, including those this process never touched. Reading
        immediately beforehand and re-applying only the deferred keys on top means a
        peer's write to a *different* key survives the flush. Without that read, one
        minion's tick would revert every foreign write since its last refresh -- and
        `set_state_to` writes into a peer's segment at 39 sites in the application.

        This is not a fix for the lost update on the *same* key: a peer writing the key
        this minion is flushing still loses, in the window between the read and the
        write. That window is the same ~10 us it has always been, because
        `__setitem__` never re-read either -- it wrote `dict(self)` from a local copy
        last refreshed by whatever call preceded it. Deferral moves the writes, it does
        not widen that window to a tick.

        Pending is cleared even when the write raises. A value the codec cannot
        represent (see `SharedBuffer.write`) would otherwise be retried on every tick
        for the rest of the run, and it would take the whole tick's other writes down
        with it every time. Dropping it matches what an immediate write does today:
        report, lose that tick's values, carry on.
        """
        if not self._pending:
            return False
        try:
            self._refresh()
            self._linked_SharedBuffer.write(dict(self))
            self._bump_generation()
            return True
        except Exception:
            print(traceback.format_exc())
            return False
        finally:
            self._pending.clear()

    @property
    def has_pending_writes(self):
        """Whether any deferred writes are queued in `_pending`, waiting for `flush`."""
        return bool(self._pending)

    def _bump_generation(self):
        """Atomically increment this segment's change counter (item 14).

        Called once per successful write, by whichever process just wrote -- owner or
        foreign. `atomicview` is opened once and held, matching `BaseMinion`'s heartbeat
        and `SharedBuffer`'s write-lock CAS: opening it per call measured far more than an
        already-open `fetch_inc()`.
        """
        if self._generation_view is None:
            self._generation_ctx = _atomics.atomicview(buffer=self._generation_shm.buf[0:4], atype=_atomics.UINT)
            self._generation_view = self._generation_ctx.__enter__()
        self._generation_view.fetch_inc()

    @property
    def generation(self):
        """This segment's change counter, read with a plain slice -- no lock, no atomics.

        Compare two samples to answer "has anything changed since I last looked",
        without diffing a value. Wraps at 2**32; a reader that only ever checks
        inequality (`last_seen != generation`) does not need to special-case the wrap.
        """
        return int.from_bytes(bytes(self._generation_shm.buf[0:4]), "little")

    def local_keys(self):
        """The key set of the local copy, without re-reading shared memory.

        Safe for a minion's own dict because its key set is only ever changed by the
        owning process: `create_state` and `remove_state` are self-operations, and the
        only cross-process writer, `set_foreign_state`, refuses a state name that is
        not already there. So a peer can change what a key holds, never which keys
        exist -- which is exactly what a membership test needs.
        """
        return super().keys()

    def local_get(self, key, default=None):
        """The local copy's value for `key`, without re-reading shared memory.

        Use only where a stale value cannot change the outcome. `set_state` uses it to
        test for the `b*` buffer prefix, and whether a state is buffer-backed is fixed
        by `create_state` in this same process.
        """
        return super().get(key, default)

    def get(self, key):
        """Refresh from shared memory, then return `dict.get(key)`.

        Narrower than `dict.get`: there is no `default` parameter, so a missing key
        always returns None rather than a caller-supplied fallback.
        """
        self._refresh()
        return super().get(key)

    def update(self, D: dict, **kwargs):
        """Merge several keys with one write.

        The buffer-prefixed keys are filtered into a new dict rather than popped out of
        `D` while iterating it, which raised RuntimeError as soon as one was present and
        mutated the caller's dict as a side effect. `kwargs` used to be accepted and
        then dropped; it is merged now, as `dict.update` implies.
        """
        payload = {k: v for k, v in dict(D, **kwargs).items() if self._BUFFER_PREFIX not in k}
        self._refresh()
        self._update(payload)
        if self._defer_writes:
            self._pending.update(payload)
            return
        self._linked_SharedBuffer.write(dict(self))
        self._bump_generation()

    def clear(self, clear_buffer=False):
        """Clear the local copy; only touches the shared segment when `clear_buffer=True`.

        Without `clear_buffer`, this diverges from `dict.clear()`'s usual guarantee: the
        local dict empties, but the next `_refresh()` (triggered by almost any other
        method) pulls the old shared state straight back in. The warning below exists so
        that mismatch does not pass silently.
        """
        self._clear()
        if clear_buffer:
            self._linked_SharedBuffer.write(dict(self))
            self._bump_generation()
        else:
            warnings.warn('SharedDict.clear() only clear its local dictionary items but not the linked shared buffer.\n'
                          'Set clear_buffer to True in order to clear the linked buffer')

    def pop(self, key):
        """Refresh, remove `key` from the local copy, and push the result to shared memory."""
        self._refresh()
        val = super().pop(key)
        self._linked_SharedBuffer.write(dict(self))
        self._bump_generation()
        return val

    def popitem(self):
        """Refresh, remove an arbitrary item from the local copy, and push the result to shared memory."""
        self._refresh()
        val = super().popitem()
        self._linked_SharedBuffer.write(dict(self))
        self._bump_generation()
        return val

    def copy(self):
        """Refresh from shared memory, then return a plain `dict` copy of the local state."""
        self._refresh()
        return super().copy()

    def items(self):
        """Refresh from shared memory, then return `dict.items()`."""
        self._refresh()
        return super().items()

    def keys(self):
        """Refresh from shared memory, then return `dict.keys()`."""
        self._refresh()
        return super().keys()

    def values(self):
        """Refresh from shared memory, then return `dict.values()`."""
        self._refresh()
        return super().values()

    @property
    def buffer_dict(self):
        """Refresh, then return the subset of items whose key carries a buffer link (`b*`-prefixed)."""
        self._refresh()
        buffer_dict = {}
        for k, v in self.items():
            if self._BUFFER_PREFIX in k:
                buffer_dict[k] = v
        return buffer_dict

    def buffer_items(self):
        """`.items()` view of `buffer_dict`."""
        return self.buffer_dict.items()

    def buffer_keys(self):
        """`.keys()` view of `buffer_dict`."""
        return self.buffer_dict.keys()

    def buffer_value(self):
        """`.values()` view of `buffer_dict`."""
        return self.buffer_dict.values()

    def unlink(self, key):
        """Remove a buffer-linked key from this dict, without releasing the buffer it points to.

        Only keys carrying the `b*` prefix may be removed this way -- it is the sole
        path around the guard in `__setitem__`/`__delitem__` that otherwise protects
        buffer-linked keys from being dropped by an ordinary `del`.
        """
        if self._BUFFER_PREFIX in key:
            super().__delitem__(key)
            self._linked_SharedBuffer.write(dict(self))
            self._bump_generation()
            print(f'The link to the buffer [{key}] has been closed')
        else:
            raise Exception(f'The buffer [{key}] cannot be found.')

    def close(self):
        """Close the generation-counter view/segment and the backing `SharedBuffer`.

        Releases this process's handles without unlinking anything, so a peer still
        attached to either segment is unaffected. Errors during teardown are caught and
        printed rather than raised, so a failed close cannot block shutdown.
        """
        try:
            if self._generation_view is not None:
                self._generation_ctx.__exit__(None, None, None)
                self._generation_view = None
            self._generation_shm.close()
            self._linked_SharedBuffer.close()
            self.is_alive = False
        except:
            print(traceback.format_exc())

    def terminate(self):
        """Close and unlink both the generation-counter segment and the backing buffer.

        Unlike `close`, this removes the segments outright and should only be called by
        the process that owns them -- see `SharedNdarray.terminate`/`SharedBuffer.terminate`
        for why a segment lingering after unlink (because a peer still holds it open) is
        expected, not an error.
        """
        try:
            if self._generation_view is not None:
                self._generation_ctx.__exit__(None, None, None)
                self._generation_view = None
            self._generation_shm.close()
            try:
                self._generation_shm.unlink()
            except FileNotFoundError:
                pass
            self._linked_SharedBuffer.terminate()
            self.is_alive = False
        except:
            print(traceback.format_exc())

    def __del__(self):
        """Best-effort release of the held-open generation-counter atomic view."""
        # The generation counter's view leaks the same way the lock byte's does when a
        # process creates a SharedDict and never closes it -- see SharedBuffer.__del__.
        try:
            if getattr(self, '_generation_view', None) is not None:
                self._generation_ctx.__exit__(None, None, None)
                self._generation_view = None
        except Exception:
            pass
