import atomics as _atomics
import datetime
import os
from time import time, perf_counter

import multiprocessing as mp
from multiprocessing import Queue, shared_memory
from queue import Empty as _QueueEmpty

import logging
import logging.config
from logging import DEBUG, INFO, WARNING, ERROR, CRITICAL

from typing import Callable

from miniPoly.core.buffer import *
# Underscore alias keeps `contract` out of this module's public namespace.
from miniPoly.core import contract as _contract

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
    """The framework's base process abstraction: lifecycle, shared state, and messaging.

    A BaseMinion is a logical worker that runs in its own OS process (spawned by
    `run`, executing `innerLoop`) and exposes its state to peers through shared
    memory rather than through the connecting Queues -- those carry only ad-hoc
    messages. Subclasses override `init_process`, `initialize`, and `main` to add
    behaviour; everything else here (state/buffer creation, linking to peers,
    status polling, heartbeats) is infrastructure shared by every minion type,
    including the GUI-facing `AbstractMinionMixin` compilers that wrap one of
    these as `_processHandler`.
    """

    @staticmethod
    def innerLoop(hook: 'BaseMinion'):
        '''
        A dirty way to put BaseMinion as a listener when suspended
        :param hook: Insert self as a hook for using self logger, main core and shutdown method
        '''
        hook._pid = os.getpid()
        hook.prepare_shared_buffer()
        hook.build_init_conn()
        STATE = hook.status
        if hook._log_config is not None:
            logging.config.dictConfig(hook._log_config)
            hook.logger = logging.getLogger(hook.name)
        hook._has_init = False
        status_read_at = perf_counter()
        # Bound once, deliberately, and reached into on purpose. The tick-boundary flush
        # has to be skipped on every iteration that wrote nothing, and that is nearly all
        # of them -- main() spins far faster than any configured interval. A local truth
        # test costs ~30 ns; calling flush_states() unconditionally cost ~0.4 us, which is
        # a quarter of the ~1.6 us iteration this loop was tuned down to in d2ec16e and
        # would have given back part of that gain. `_shared_dict` is never replaced after
        # prepare_shared_buffer, so the binding cannot go stale.
        pending_states = hook._shared_dict._pending
        # Held open once rather than reopened per tick: opening an atomicview measured
        # ~80 us against ~20 us for an increment through one already held open, and both
        # dwarf the plain-slice read a peer does (roadmap item 16, budget note in 2.2).
        heartbeat_view = hook._heartbeat_view
        heartbeat_at = perf_counter()
        # Everything below is guarded. An unhandled exception in init_process(),
        # initialize() or main() used to kill the child while its status segment kept
        # reporting the last value written to it, so is_alive() stayed True for every
        # peer and AbstractGUIAPP.shutdown() could never finish (B2). Device and Qt
        # setup both happen in initialize(), which is exactly where such an exception
        # comes from. `finally` guarantees _shutdown() runs, and _shutdown() is what
        # marks the minion dead for its peers.
        try:
            hook.init_process()
            while STATE >= 0:
                if STATE == 1:
                    if hook._is_suspended:
                        hook._is_suspended = False
                    if not hook._has_init:
                        hook.initialize()
                        hook._has_init = True
                        # Every APP shell builds its compiler inside initialize(), so this
                        # is the framework's own view of "application-side declaration is
                        # finished" -- one call site covering every minion type, with
                        # nothing for a compiler author to remember. See B11 and
                        # seal_declarations. Note the heartbeat below cannot substitute:
                        # initialize() runs *inside* this loop, so a peer still building
                        # its compiler has a heartbeat frozen at 0 and is indistinguishable
                        # from a hung one by that signal alone.
                        hook.seal_declarations()
                    hook.main()
                    # The tick boundary, and the only place a deferred state write
                    # becomes visible to peers. See the binding above for why the test
                    # is inline rather than a call into flush_states().
                    if pending_states:
                        hook.flush_states()
                elif STATE == 0:
                    if not hook._is_suspended:
                        hook.info(hook.name + " is suspended\n")
                        hook._is_suspended = True
                        hook._has_init = False
                    sleep(.1)
                # Rate-limited: see STATUS_POLL_INTERVAL. This used to re-read the status
                # on every single iteration, which is what made the tick loop expensive.
                now = perf_counter()
                if now - status_read_at >= hook.STATUS_POLL_INTERVAL:
                    status_read_at = now
                    try:
                        STATE = hook.status
                    except:
                        pass
                        # print(f'{hook.name}: {traceback.format_exc()}')
                # Deliberately outside the STATE==1 branch, sharing `now` with the status
                # poll above: a suspended minion's loop is still alive by design, so its
                # heartbeat should keep advancing while STATE==0, distinct from a hung or
                # crashed process where this line is never reached at all -- there is no
                # code path back to here if init_process(), initialize() or main() never
                # returns. See roadmap item 16 and BaseMinion.heartbeat_of.
                if now - heartbeat_at >= hook.HEARTBEAT_INTERVAL:
                    heartbeat_at = now
                    heartbeat_view.fetch_inc()
        except Exception:
            # Reported twice on purpose: a crash inside initialize() can happen before
            # the logger queue is usable, and then stderr is the only channel left.
            hook.error(f'{hook.name} died with an unhandled exception:\n{traceback.format_exc()}')
            traceback.print_exc()
        finally:
            hook._shutdown()

    _INDEX_SHARED_BUFFER_SIZE = 2 ** 13  # The size allocated for storing small shared values/array, each write takes <2 ms

    #: Upper bound, in seconds, on how stale innerLoop's cached status may be -- so also
    #: the worst-case delay before a shutdown or suspend is noticed.
    #:
    #: The loop used to re-read the status on every iteration, and `status` is a real
    #: SharedNdarray.read(): take the segment's lock byte, copy the array, release. Measured
    #: in situ (iterations counted between callback fires, which is the only trustworthy way
    #: -- a microbenchmark of read() in isolation overstated its cost by ~6x): the read is
    #: ~1.3 us of a ~2.9 us iteration, and the loop ran ~340 000 iterations per second at
    #: every configured interval, so each minion performed ~340 000 lock acquire/release
    #: cycles per second on its own status segment.
    #:
    #: At 5 ms that becomes 200 reads per second -- roughly 1700x less lock traffic -- and
    #: the iteration drops to ~1.6 us, so the loop runs ~1.85x more often and the fire
    #: instant is resolved *finer* rather than coarser. Measured tick jitter at a 1 ms
    #: interval improved from 0.067-0.172 ms to 0.006-0.050 ms. CPU occupancy is unchanged
    #: at ~99 %: the thread still spins, and nothing can lower that without sleeping.
    #:
    #: It also relieves the contention introduced by making SharedNdarray.write() take the
    #: write lock (defect A4): a peer writing this minion's status during shutdown no longer
    #: has to find a gap between hundreds of thousands of acquisitions per second.
    #:
    #: A fixed bound rather than one tick, so the guarantee does not get worse as the tick
    #: interval grows -- a camera at 20 ms still reacts within 5 ms. See docs/PROJECT_OVERVIEW.md
    #: section 2.3 for why the loop spins at all instead of sleeping.
    STATUS_POLL_INTERVAL = 0.005

    #: How often `innerLoop` bumps this minion's heartbeat counter (roadmap item 16).
    #: 10 Hz, matching the read side: a peer samples at the same order of frequency, so
    #: bumping faster would only add `atomics.fetch_inc()` cost (measured ~20 us held
    #: open, versus 0.4-0.8 us for a peer's plain-slice read) without being observable.
    #: The counter is not a tick-rate meter -- a minion configured well above 10 Hz still
    #: only bumps once per interval -- it is a liveness signal: frozen means the process
    #: is not reaching this line, whether because it crashed, hung inside `main()`, or
    #: (see `_shutdown`) exited cleanly and unlinked the segment.
    HEARTBEAT_INTERVAL = 0.1

    def __init__(self, name):
        """Initialize bookkeeping for a not-yet-started minion; no shared memory is created here."""

        self.logger = None
        self._log_config = None
        self.Process = None
        self._shared_dict = None
        self._is_suspended = False
        self._pid = None
        self._heartbeat_shm = None
        self._heartbeat_ctx = None
        self._heartbeat_view = None
        # Peers' heartbeat segments this process has attached to, by minion name --
        # cached the same way `_registered_buffer_handle` is, so `heartbeat_of` opens
        # each one at most once. Never populated for this minion's own segment.
        self._registered_heartbeat = {}
        # (minion, state) pairs already reported as unknown, so the report happens once
        # instead of once per poll. See get_foreign_state.
        self._unknown_state_reported = set()

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
        self._registered_buffer_handle = {}
        self.minion_to_link = []

    ############# Logging module #############
    def attach_logger(self, logger: 'LoggerMinion'):
        """Wire this minion's logging calls to a running LoggerMinion's queue.

        Must be called before `prepare_shared_buffer`/`run` for messages logged
        during startup to reach the listener; the actual `logging.config.dictConfig`
        call happens later, inside `innerLoop`, using the config stashed here.
        """
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
        """Forward to the attached logger, or silently drop the message if none is attached yet."""
        if self.logger is not None:
            self.logger.log(*args)
        # else:
        #     warnings.warn("[{}]-[Warning] Logger unattached".format(self.name))

    def debug(self, msg):
        """Log `msg` at DEBUG level."""
        self.log(logging.DEBUG, msg)

    def info(self, msg):
        """Log `msg` at INFO level."""
        self.log(logging.INFO, msg)

    def warning(self, msg):
        """Log `msg` at WARNING level."""
        self.log(logging.WARNING, msg)

    def error(self, msg):
        """Log `msg` at ERROR level."""
        self.log(logging.ERROR, msg)

    ############# shared buffer/state module #############

    def prepare_shared_buffer(self):
        """Create this minion's SharedDict, status state, and heartbeat segment.

        Called exactly once, by `innerLoop` in the child process right after fork,
        before `build_init_conn` or any peer can link to this minion -- so a peer
        that successfully finds this minion's SharedDict is guaranteed to also find
        FRAMEWORK_SEALED (even if still False) and the status/heartbeat segments.
        Must run before any `create_state`/`set_state` call, since those write
        through `_shared_dict`, which does not exist until this returns.
        """
        self._shared_dict = SharedDict(f'{self.name}_shared_dict', lock=self.lock, create=True, name=self.name,
                                       size=self._INDEX_SHARED_BUFFER_SIZE)
        self.create_state(_contract.FRAMEWORK_STATUS, 1,
                          use_buffer=True)  # create a shared state for the minion status which will be stored in an independent shared buffer
        self._shared_dict['name'] = self.name
        # Seeded here rather than through create_state so it exists from the instant the
        # segment does: a peer that can link at all can always read it, and never has to
        # treat "the flag is missing" as a third case. See seal_declarations.
        self._shared_dict[_contract.FRAMEWORK_SEALED] = False
        # A tick's set_state calls become one encode and one write, flushed by innerLoop
        # once main() returns. See flush_states and SharedDict.flush.
        self._shared_dict.defer_writes(True)
        self._shared_dict.flush()

        # A raw segment, deliberately not a SharedBuffer/SharedNdarray: the whole point
        # (roadmap item 16) is a counter a peer can read with a plain byte slice, no
        # lock, no codec. Named by convention like `_status_name`, but without its `b*`
        # prefix -- this is not a SharedDict-referenced buffer, so nothing should look it
        # up through a linked minion's state dict; a peer that has this minion's name at
        # all can attach directly. `atomicview` is opened once and held for the escaping
        # of `_heartbeat_ctx`/`_heartbeat_view` for `innerLoop` and `_shutdown` to use --
        # opening it per call measured ~4x an already-open `fetch_inc()` (2.2's budget
        # note: an atomic operation may appear at most once per tick per segment).
        self._heartbeat_shm = shared_memory.SharedMemory(
            create=True, name=f"{self.name}_heartbeat", size=4)
        self._heartbeat_shm.buf[0:4] = (0).to_bytes(4, "little")
        self._heartbeat_ctx = _atomics.atomicview(buffer=self._heartbeat_shm.buf, atype=_atomics.UINT)
        self._heartbeat_view = self._heartbeat_ctx.__enter__()

    def flush_states(self):
        """Push this tick's deferred state writes to shared memory. Cheap when idle.

        Called by `innerLoop` after every `main()`, so it runs at the framework's own
        tick rate and must cost nothing when there is nothing to write -- with no
        pending keys it is one dict truth test. `main()` spins far faster than any
        configured interval, so the empty case is overwhelmingly the common one.
        """
        if self._shared_dict is not None:
            try:
                self._shared_dict.flush()
            except Exception:
                # Never let a flush failure escape into innerLoop's crash handler: the
                # tick's values are already lost, and killing the minion over it would
                # turn a dropped sample into a dead process.
                self.log(logging.WARNING, f"Failed to flush states:\n{traceback.format_exc()}")

    def seal_declarations(self):
        """Publish `FRAMEWORK_SEALED`: this minion's initial state namespace is complete.

        Called by `innerLoop` the moment `initialize()` returns, which for every APP shell
        is the moment the compiler's `__init__` returns -- the compiler class is passed in
        and instantiated there on purpose (see processor/prototypes.py), so the framework
        knows when application-side declaration is done without the application saying so.

        Written straight through rather than through `set_state`, for the same reason
        `create_state` flushes: a peer blocked waiting for a state must see the seal on
        this side of the tick boundary, not at the end of the tick.

        Idempotent, and re-run after a suspend/resume cycle re-runs `initialize()`.
        """
        if self._shared_dict is None:
            return
        self._shared_dict[_contract.FRAMEWORK_SEALED] = True
        self._shared_dict.flush()

    def declarations_sealed_by(self, minion_name: str):
        """Whether a linked peer has published `FRAMEWORK_SEALED`.

        Returns None when it cannot be told -- the peer is not linked, or its segment
        predates the flag -- so a caller must treat None as "keep waiting", never as
        "sealed". `get_foreign_state` is the only caller.
        """
        if minion_name == self.name:
            if self._shared_dict is None:
                return None  # parent process, before prepare_shared_buffer
            return bool(self._shared_dict.local_get(_contract.FRAMEWORK_SEALED))
        handle = self._registered_buffer_handle.get(minion_name, {}).get('shared_dict')
        if handle is None:
            return None
        # `get` and not `local_get`: the local copy is only as fresh as the last read, and
        # the whole point is to observe a flag the peer sets after we linked to it.
        sealed = handle.get(_contract.FRAMEWORK_SEALED)
        return None if sealed is None else bool(sealed)

    def build_init_conn(self, timeout=1000):
        """Retry `link_minion` for every declared peer until all succeed or `timeout` (ms) elapses.

        Called once by `innerLoop` right after `prepare_shared_buffer`. Peers
        started in the same batch may not have created their SharedDict yet, hence
        the retry loop rather than a single attempt. There is no return value or
        exception for a peer still unlinked when the timeout expires -- a caller
        that needs to know must check `_linked_minion` itself.
        """
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
        """Back a new shared state with a `SharedNdarray` instead of the SharedDict.

        Used by `create_state(..., use_buffer=True)` for values that need
        lock-free, fixed-size access (e.g. images, high-frequency samples) rather
        than the SharedDict's decode-on-read semantics. Records an indirection
        entry (`name -> 'b*{minion}_{name}'`) in `_shared_dict` so peers doing a
        normal `get_state` transparently follow it via `_read_buffer_as_state`.
        Scalars and list/tuple inputs are coerced to a 1-element/1-D `ndarray`
        first, since `SharedNdarray` only stores arrays.
        """
        # The reference name of any shared buffer should have the structure 'b*{minion_name}_{buffer_name}' The
        # builtin state dictionary for all minions are the SharedDict whose name is 'b*{self.name}_shared_dict'
        # The names of all other buffers created later will be saved in the builtin SharedDict as a shared state as
        # name-value pairs: {shared_buffer_reference_name}: {shared_buffer_name};
        # #
        # For safety consideration, it is compulsory to use "with" statement to access any foreign buffers.

        if type(data) in [list, tuple]:
            data = np.array(data)
        elif type(data) in [int, float, bool]:
            data = np.array([data], dtype=type(data))
        elif type(data) == np.ndarray:
            pass
        else:
            raise TypeError(f"Data type {type(data)} is not supported")
        if dtype is not None:
            data = data.astype(dtype)

        if name not in self._shared_dict.keys():
            shared_buffer_name = f"{self.name}_{name}"
            try:
                self._shared_buffer[f"b*{shared_buffer_name}"] = SharedNdarray(shared_buffer_name, self.lock,
                                                                               data)  # The list '_shared_buffer" host all local buffer for other minion to access, it also serves as a handle hub for later closing these buffers
            except Exception:
                self.log(logging.ERROR, f"Error in creating buffer '{name}'.\n{traceback.format_exc()}")
            self._shared_dict[
                name] = f"b*{shared_buffer_name}"  # e.g. 'status': 'b*{self.name}_status' -> 'b*{self.name}_status': '{self.name}_status'
        else:
            self.log(logging.ERROR, f"SharedBuffer '{name}' already exist")

    def remove_shared_buffer(self, state_name: str):
        """Close and forget a locally-created shared buffer by its `_shared_buffer` key."""
        if state_name in self._shared_buffer.keys():
            self._shared_buffer[state_name].close()
            del self._shared_buffer[state_name]
        else:
            self.log(logging.ERROR, f"State '{state_name}' cannot be deleted because it does not exist")

    def link_minion(self, minion_name):
        """Attach to a peer's SharedDict and register handles for its buffer-backed states.

        Idempotent: a `minion_name` already present in `_linked_minion` is a no-op
        that just logs and returns 0. Opening the peer's SharedDict is done through
        a throwaway `with` block purely to validate its `'name'` state matches
        `minion_name` -- protects against stale or wrongly-named segments left over
        from a previous run -- after which a second, kept-open handle is opened for
        real use. Returns 0 on success, -1 if the peer's segment does not exist yet
        (the peer hasn't reached `prepare_shared_buffer`), or 1/2 for a name
        mismatch or any other failure; `build_init_conn` polls this in a loop until
        it returns 0 for every declared peer.
        """
        err = 0
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
                        self._linked_minion[minion_name] = [
                            'shared_dict']  # The name of the shared buffer from this minion

                        # To register all shared buffer from the linked minion
                        # A default shared buffer is 'status'
                        for k, v in tmp_dict.items():
                            if type(v) == str:
                                if v.startswith(_contract.BUFFER_PREFIX):
                                    self._linked_minion[minion_name].append(k)
                    else:
                        self.log(logging.ERROR,
                                 f'[{self.name}] Pre-execution error: The "name" state of the linked shared buffer {dict_name} is inconsistent with input minion name {minion_name}.')
                        err = 1

                if err == 0:
                    self._registered_buffer_handle[minion_name] = {}
                    for k in self._linked_minion[minion_name]:
                        if k != 'shared_dict':
                            buf = SharedNdarray(f"{minion_name}_{k}", lock=self.lock, create=False)
                        else:
                            buf = SharedDict(f"{minion_name}_shared_dict", lock=self.lock, create=False)
                        self._registered_buffer_handle[minion_name][k] = buf

            except FileNotFoundError:
                self.log(logging.INFO, f"SharedDict '{minion_name} not found'.")
                err = -1
            except:
                self.log(logging.ERROR, f"Error when connecting to '{minion_name}'.\n{traceback.format_exc()}")
                err = 2
        else:
            self.log(logging.INFO, f"Already linked to minion: {minion_name}")
        return err

    def create_state(self, state_name: str, state_val: object, use_buffer: bool = False, dtype=None):
        """Declare a new shared state, dict-backed by default or buffer-backed when `use_buffer`.

        Refuses to overwrite an existing state of the same name (logs an error and
        returns instead). Flushes immediately rather than deferring to the tick
        boundary -- see the inline note on the dict branch -- because peers
        discover new states by polling for them, and a declaration is expected to
        happen once at startup, so the extra write is free in steady state.
        """
        if state_name in self._shared_dict.keys():
            self.log(logging.ERROR, f"State '{state_name}' already exists")
        else:
            if use_buffer:
                self.create_shared_buffer(state_name, state_val, dtype=dtype)
            else:
                self._shared_dict[state_name] = state_val
                # A declaration is published immediately, never deferred to the tick
                # boundary. Peers discover states by polling for them and already lose
                # that race often enough to be worth a defect entry (B11); holding a new
                # state back for a tick would only widen it. Declarations happen at
                # startup, so the extra write costs nothing in steady state.
                self._shared_dict.flush()
            self.log(logging.INFO, f"Shared state: '{state_name}' created")

    def remove_state(self, state_name: str):
        """Delete a shared state, whichever storage (SharedDict or SharedBuffer) backs it."""
        if state_name in self._shared_dict.keys():
            del self._shared_dict[state_name]
            self.log(logging.INFO, f"Shared state: '{state_name}' DELETED")
        elif state_name in self._shared_buffer.keys():
            self._shared_buffer[state_name].close()
            del self._shared_buffer[state_name]
        else:
            self.log(logging.ERROR, f"State '{state_name}' cannot be deleted because it does not exist")

    def has_state(self, state_name: str):
        """Whether `state_name` exists in this minion's own SharedDict."""
        return state_name in self._shared_dict.keys()

    def has_foreign_state(self, minion_name, state_name):
        """Check whether a linked peer currently exposes `state_name`.

        Returns False -- never None -- for every failure mode: an unknown (unlinked)
        minion, a dead one, or a live one that simply has not declared the key. Both
        of the first two also log an error, since they mean the caller's wiring is
        wrong rather than the state merely being absent.

        A hit in the local `_linked_minion` cache is trusted without touching shared
        memory; only a miss falls through to reading the peer's live SharedDict, so a
        key that has been declared since the link was made is still found.
        """
        has_state = False
        if minion_name in self._linked_minion.keys():
            if state_name in self._linked_minion[minion_name]:
                has_state = True
            else:
                if self.is_minion_alive(minion_name):
                    has_state = state_name in list(self._registered_buffer_handle[minion_name]['shared_dict'].keys())
                else:
                    self.error(f"Dead minion: '{minion_name}'")
        else:
            self.log(logging.ERROR, f"Unknown minion: '{minion_name}'")
        return has_state

    def get_shared_state_names(self, minion_name: str):
        """
        Get the names of all shared states in the minion's shared dictionary
        Will soon be deprecated
        """
        if minion_name == self.name:
            return list(self._shared_dict.keys())

        elif minion_name in self._linked_minion.keys():
            if self.is_minion_alive(minion_name):
                return list(self._registered_buffer_handle[minion_name]['shared_dict'].keys())
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
            obj: None if any error occurs in the core
        """
        state_val = None
        if minion_name == self.name:
            state_val = self.get_state(state_name)
        elif minion_name in self._linked_minion.keys():
            state_val = self.get_foreign_state(minion_name, state_name)
        else:
            self.error(f"Unknown minion: '{minion_name}'")

        return state_val

    def get_state(self, state_name: str, asis=False):
        """Read a state from this minion's own SharedDict, transparently following buffer indirection.

        `state_name='ALL'` returns a dict snapshot of every state, each resolved
        the same way a single lookup would be. `asis=True` keeps a buffer-backed
        single-element state as a 1-element ndarray instead of unwrapping it to a
        scalar -- see `_read_buffer_as_state`. Returns None (after logging an
        error) for an unknown name rather than raising, since callers poll for
        states that may not exist yet.
        """
        # param asis: if true, then keep the format of the state (e.g. state is an integer stored in a ndarray buffer,
        # asis == True, the state will be return as a numpy array
        state_val = None  # Return None if exception to avoid error
        if state_name in self._shared_dict.keys():
            state_val = self._shared_dict.get(state_name)
            if type(state_val) == str:
                if state_val.startswith(_contract.BUFFER_PREFIX):
                    state_val = self._read_buffer_as_state(state_val, asis)
        elif state_name == 'ALL':
            state_val = dict(self._shared_dict)
            for i_state_name, i_state_val in state_val.items():
                if type(i_state_val) == str:
                    if i_state_val.startswith(_contract.BUFFER_PREFIX):
                        state_val[i_state_name] = self._read_buffer_as_state(i_state_val, asis)
        else:
            self.error(f"Unknown state: '{state_name}'")
        return state_val

    def get_foreign_state(self, minion_name, state_name, asis=False, timeout=3000):
        """Read a state from a linked peer, retrying for up to `timeout` ms if not yet visible.

        Mirrors `get_state` for a foreign minion, but a peer's SharedDict can lag
        behind its declarations (see B11), so a miss is retried every 10 ms rather
        than treated as an immediate error -- unless the peer has already
        published `FRAMEWORK_SEALED` (see `declarations_sealed_by`), in which case
        it truly will never appear and the loop exits early instead of burning the
        full timeout on the caller's own tick. The first time a buffer-backed
        state is discovered, its name is cached into `_linked_minion`/
        `_registered_buffer_handle` so later reads skip straight to
        `_read_foreign_buffer_as_state`. An unknown state is logged once per
        (minion, state) pair via `_unknown_state_reported`, not on every failed
        poll. Returns None, with an error logged, if the peer is dead or the state
        never appears.
        """
        # param asis: if true, then keep the format of the state (e.g. state is an integer stored in a ndarray buffer,
        # asis == True, the state will be return as a numpy array
        state_val = None
        err_code = 0
        if self.is_minion_alive(minion_name):
            if state_name in self._linked_minion[minion_name]:
                state_val = self._read_foreign_buffer_as_state(minion_name, state_name, asis)
            else:
                shared_dict = self._registered_buffer_handle[minion_name]['shared_dict']
                for i in range(int(timeout / 10)):
                    # Reset per attempt. Without this a single miss latched err_code at 1
                    # for the rest of the loop, so `break` below could never fire again:
                    # the wait ran all `timeout/10` iterations even when the state showed
                    # up on the second attempt, and then reported it as unknown while
                    # returning the value it had just read.
                    err_code = 0
                    if state_name in shared_dict.keys():
                        state_val = shared_dict[state_name]
                        if type(state_val) == str:
                            if state_val.startswith(_contract.BUFFER_PREFIX):
                                self._linked_minion[minion_name].append(state_name)
                                self._registered_buffer_handle[minion_name][state_name] = SharedNdarray(f"{minion_name}_{state_name}", lock=self.lock, create=False)
                                state_val = self._read_foreign_buffer_as_state(minion_name, state_name, asis)
                    elif state_name == 'ALL':
                        state_val = dict(shared_dict)
                        for i_state_name, i_state_val in state_val.items():
                            if type(i_state_val) == str:
                                if i_state_val.startswith(_contract.BUFFER_PREFIX):
                                    state_val[i_state_name] = self._read_foreign_buffer_as_state(minion_name, i_state_name,
                                                                                                 asis)
                    else:
                        err_code = 1

                    if err_code == 0:
                        break
                    # A sealed peer has finished declaring, so waiting cannot help. Without
                    # this the loop spins the full `timeout` on every miss, inside the
                    # caller's own tick: for the GUI that is 3 s of frozen Qt event loop,
                    # seen three times in one session for camera buffers whose names come
                    # from a runtime video format (defect B11). An unsealed peer is still
                    # constructing its compiler, so the wait is exactly what is wanted and
                    # the retry is unchanged. The extra decode this costs is one per failed
                    # attempt, against the 10 ms sleep on the same path.
                    if self.declarations_sealed_by(minion_name):
                        break
                    sleep(0.01)

        else:
            err_code = 2

        if err_code == 1:
            # Reported once per (minion, state). Each miss used to cost a full `timeout`
            # spin, which rate-limited this log by accident; failing fast on a sealed peer
            # removes that, and a GUI polling a not-yet-created camera buffer would
            # otherwise log on every tick. Cleared on the first successful read, so a state
            # that arrives late reports once and then goes quiet.
            if (minion_name, state_name) not in self._unknown_state_reported:
                self._unknown_state_reported.add((minion_name, state_name))
                self.error(f"Unknown foreign state '{state_name}' in minion '{minion_name}'")
        elif err_code == 2:
            self.error(f"Dead minion '{minion_name}' or errors in connecting to its shared buffer")
        else:
            self._unknown_state_reported.discard((minion_name, state_name))

        return state_val

    def _read_foreign_buffer_as_state(self, minion_name, state_name, asis):
        """Read a peer's buffer-backed state, unwrapping a 1-element array to a scalar unless `asis`."""
        shm = self._registered_buffer_handle[minion_name][state_name]
        state_val = shm.read()
        if state_val.size == 1 and not asis:
            state_val = state_val[0]
        return state_val

    def _read_buffer_as_state(self, state_name, asis):
        """Read this minion's own buffer-backed state, unwrapping a 1-element array to a scalar unless `asis`."""
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
        """Write a state's value, going through the SharedDict or its backing buffer as needed.

        Checks `local_keys()`/`local_get()` first rather than the fresh `keys()`/
        `[...]`, since only this process can change which states exist or which
        are buffer-backed -- a state's *existence* never needs a fresh read, only
        its value does. A local miss triggers one `get()` to rule out a stale
        local copy before the state is reported unknown. When the state is
        buffer-backed, any pending SharedDict writes are flushed first:
        SharedDict writes are deferred to the tick boundary while a SharedNdarray
        write lands immediately, so writing the buffer without flushing first
        could let it become visible to a peer *before* dict writes made earlier
        in the same tick -- see the inline note for the SaveDir/StreamToDisk
        ordering bug this fixes.
        """
        # `local_keys`/`local_get` rather than `keys()`/`[...]`: both of those re-read
        # and re-decode the whole segment, so writing one state cost two full reads
        # before it cost a write -- 24 decodes per tick for SERVO's 12 states. Neither
        # test needs a fresh value: only this process changes which states exist or
        # which are buffer-backed. See SharedDict.local_keys for why that holds.
        if state_name not in self._shared_dict.local_keys():
            # A miss is re-checked against shared memory before it is believed.
            # `_refresh()` clears the local copy before rebuilding it, so ten failed
            # reads in a row -- a torn write, a lock acquire that timed out -- leave it
            # empty; reporting the state unknown on that basis would be permanent,
            # since nothing else on this path reads the segment again. Costs a refresh
            # only on the error path, which is where the old code paid it every time.
            self._shared_dict.get(state_name)
        if state_name in self._shared_dict.local_keys():
            stored_value = self._shared_dict.local_get(state_name)
            state_type = 'dict_val'
            if type(stored_value) == str:
                if stored_value.startswith(_contract.BUFFER_PREFIX):
                    state_type = 'buffer'
                    state_name = stored_value

            if state_type == 'dict_val':
                self._shared_dict[state_name] = state_val
            elif state_type == 'buffer':
                # Flush first, or a buffer-backed write overtakes the dict writes made
                # before it in the same tick. The two storages have different visibility:
                # a `SharedNdarray` write lands immediately, while `SharedDict` writes are
                # coalesced and published at the tick boundary (roadmap item 10). So a
                # minion that sets a directory and *then* raises a "start" flag -- which
                # is exactly what the application's GUI does with SaveDir and
                # StreamToDisk -- publishes the flag first, and a peer polling in that
                # window sees "start" with the previous directory. It cost one session's
                # SCAN recording on 2026-08-06 to notice.
                #
                # Only pays when a tick mixes both kinds, and only for the writes already
                # queued: `flush()` returns immediately when nothing is pending, which is
                # the common case on the read-heavy paths.
                self._shared_dict.flush()
                self._shared_buffer[state_name].write(state_val)
        else:
            self.error(f"Unknown state: '{state_name}'")
        return state_val

    def set_foreign_state(self, minion_name, state_name, state_val):
        """Write a state on a linked peer, going through its SharedDict or buffer handle as needed.

        Mirrors `set_state` for a foreign minion: if `state_name` is discovered to
        have become buffer-backed since it was first linked, the buffer handle is
        opened and cached the same way `get_foreign_state` does. Logs and no-ops
        (rather than raising) if the peer is dead or the state does not exist.
        """
        err_code = 0
        if self.is_minion_alive(minion_name):
            if state_name in self._linked_minion[minion_name]:
                self._registered_buffer_handle[minion_name][state_name].write(state_val)
            else:
                shared_dict = self._registered_buffer_handle[minion_name]['shared_dict']
                if state_name in shared_dict.keys():
                    # In case the state has been changed to buffer type, this section will update the linked_minion list
                    stored_val = shared_dict[state_name]
                    state_type = 'dict_val'
                    if type(stored_val) == str:
                        if stored_val.startswith(_contract.BUFFER_PREFIX):
                            self._linked_minion[minion_name].append(state_name)
                            self._registered_buffer_handle[minion_name][state_name] = SharedNdarray(
                                f"{minion_name}_{state_name}", lock=self.lock, create=False)
                            state_type = 'buffer'
                    if state_type == "dict_val":
                        shared_dict[state_name] = state_val
                    else:
                        self._registered_buffer_handle[minion_name][state_name].write(state_val)
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
        """Establish a bidirectional message Queue with `minion` and queue it for `link_minion`.

        Reuses an existing Queue if `minion` already created one for this pairing
        (whichever side calls `connect` first wins), calling `minion.connect(self)`
        back so both sides end up with the same Queue object. Only registers the
        Queue and records `minion.name` in `minion_to_link` -- the actual
        shared-state link happens later, in `build_init_conn`, once both processes
        are running.
        """
        if minion._queue.get(self.name) is not None:
            self._queue[minion.name] = minion._queue[self.name]
        else:
            self._queue[minion.name] = Queue()
            minion.connect(self)
        # self.link_minion(minion.name)
        self.minion_to_link.append(minion.name)

    def disconnect(self, minion_name):
        """Tear down every connection artifact for `minion_name`, tolerating partial state.

        Called both for a normal disconnect and, from `send`/`get`, when a peer is
        discovered to have died -- and from `_shutdown` for every remaining peer.
        See the inline note below for why every lookup here is tolerant rather
        than a `[...]` that would raise.
        """
        # Every lookup here tolerates a missing key. connect() populates only _queue;
        # _registered_buffer_handle and _linked_minion are populated only by a
        # *successful* link_minion. A peer that was not up within build_init_conn's 1 s
        # timeout -- easy with eight processes starting serially plus camera DLL
        # initialisation -- therefore has a queue and no handles, and the KeyError this
        # used to raise aborted the rest of _shutdown(), so the shared segments were
        # never terminated (B3).
        for i_buf in self._registered_buffer_handle.get(minion_name, {}).values():
            try:
                i_buf.close()
            except Exception as e:
                self.log(logging.WARNING, "Error in closing buffer: {}".format(e))
        self._registered_buffer_handle.pop(minion_name, None)
        heartbeat_handle = self._registered_heartbeat.pop(minion_name, None)
        if heartbeat_handle is not None:
            try:
                heartbeat_handle.close()
            except Exception as e:
                self.log(logging.WARNING, "Error in closing heartbeat handle: {}".format(e))
        self._linked_minion.pop(minion_name, None)
        queue = self._queue.pop(minion_name, None)
        if queue is not None:
            try:
                queue.close()
            except Exception as e:
                self.log(logging.WARNING, "Error in closing queue: {}".format(e))

    ############# Pipe communication module #############

    def send(self, tgt_name, msg_val, msg_type=None):
        """Enqueue `(msg_val, msg_type)` on the connection queue to `tgt_name`.

        Guarded by this minion's own `status` rather than the target's -- if this
        minion is not in the running state, the send is refused and `tgt_name` is
        disconnected instead of queued. Also refuses (without disconnecting) a
        target with no such queue, or a full queue.
        """
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
        """Blocking-style receive of one `(msg_val, msg_type)` pair from `src_name`'s queue.

        Returns `(None, None)` for an empty queue (expected and logged at DEBUG)
        or a terminated minion (`status < 0`, logged as an error and followed by a
        `disconnect(src_name)`) -- callers must check for `(None, None)` rather
        than assume a message is always present. See `get_nowait` for the
        non-logging variant used on hot polling paths.
        """
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

    def get_nowait(self, src_name):
        """Return one queued message without logging an expected empty queue."""
        chn = self._queue[src_name]
        if chn is None or self.status < 0:
            return None, None
        try:
            msg_val, msg_type = chn.get_nowait()
        except _QueueEmpty:
            return None, None
        return msg_val, msg_type

    ############# Status checking module #############

    @property
    def status(self):
        """This minion's own lifecycle status (see innerLoop's STATE values), read from shared memory."""
        return self._shared_buffer[self._status_name].read()

    @status.setter
    def status(self, value):
        """Write this minion's lifecycle status to shared memory, visible to peers immediately (no lock-step tick boundary)."""
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
                shm = self._registered_buffer_handle[minion_name]['status']
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

    def heartbeat_of(self, minion_name: str):
        """The raw tick counter of a linked peer, read with no lock (roadmap item 16).

        Complements `is_minion_alive`, which trusts the *last value the peer wrote* to
        its status segment -- correct for a graceful `shutdown()`, blind to a peer that
        is genuinely stuck inside `main()` with status still reading 1. This counter
        answers a different question: is that peer's `innerLoop` still reaching the
        bottom of its own loop at all? Two samples taken `HEARTBEAT_INTERVAL` or more
        apart that come back equal mean it is not, regardless of what `status` claims --
        crashed, deadlocked, or blocked on something that never returns.

        `None` means the peer's heartbeat segment could not be read: either it was never
        linked, or -- because this reads a raw segment outside the lock/codec machinery
        that `is_minion_alive` goes through -- because the peer has already unlinked it
        in `_shutdown`, which is itself a clean-exit signal distinct from "still running
        but frozen". Callers that need to tell those two apart should combine this with
        `is_minion_alive`.

        Returns:
            int or None: the peer's tick counter, or None if it cannot be read.
        """
        if minion_name not in self._linked_minion.keys():
            self.error(f"Minion '{minion_name}' is not connected")
            return None
        handle = self._registered_heartbeat.get(minion_name)
        if handle is None:
            try:
                handle = shared_memory.SharedMemory(name=f"{minion_name}_heartbeat")
            except FileNotFoundError:
                return None
            self._registered_heartbeat[minion_name] = handle
        try:
            return int.from_bytes(bytes(handle.buf[0:4]), "little")
        except Exception:
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
            # 1. check buffer name in the foreign minion shared dict
            shared_dict = self._registered_buffer_handle[minion_name]['shared_dict']
            if buffer_name not in shared_dict.keys():
                self.error(f"Unknown foreign buffer '{buffer_name}' in minion '{minion_name}'")
                return None
            else:
                # 2. update the registered buffer handle
                if buffer_name not in self._registered_buffer_handle[minion_name].keys():
                    self._registered_buffer_handle[minion_name][buffer_name] = SharedNdarray(
                        f"{minion_name}_{buffer_name}", lock=self.lock, create=False)
            try:
                ISALIVE = self._registered_buffer_handle[minion_name][buffer_name].is_alive()
                return ISALIVE
            except FileNotFoundError:
                self.log(logging.INFO, f"Linked shared buffer '{minion_name}_{buffer_name}' is closed.")
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
        """Spawn the OS process that executes `innerLoop` for this minion."""
        self.Process = mp.Process(target=BaseMinion.innerLoop, args=(self,))
        self.Process.start()

    def initialize(self):
        """Subclass hook, run by `innerLoop` on entering the running state (and again after a suspend/resume cycle). No-op by default."""
        pass

    def init_process(self):
        """Subclass hook, run by `innerLoop` exactly once before the tick loop starts. No-op by default."""
        pass

    def main(self):
        """Subclass hook, run by `innerLoop` once per tick while the minion is running. No-op by default."""
        pass

    def shutdown(self):
        """Request a graceful stop by setting `status` to -1; `innerLoop` notices on its next status poll and exits its own loop into `_shutdown`."""
        self.status = -1

    def _shutdown(self):
        """Tear down this minion's process-local and shared resources; always run by `innerLoop`'s `finally`.

        Order matters: pending state writes are flushed before the segments they
        live in are terminated; `status` is set to -2 (dead, distinct from the -1
        `shutdown()` request) even if no logger is attached, since that value is
        the only way peers learn this minion is gone; every remaining connection
        is `disconnect`-ed; and the heartbeat segment is unlinked last, so a
        peer's `heartbeat_of` reading `FileNotFoundError` after this point is a
        reliable clean-exit signal. Never raises on its own account -- every step
        that talks to the OS or shared memory is wrapped so one failure doesn't
        stop the rest of cleanup from running.
        """
        if self.logger is not None:
            self.log(logging.INFO, self.name + " is off")

        # Before the segment is torn down: whatever the last tick wrote is still only in
        # the pending dict if main() raised between the write and innerLoop's flush.
        self.flush_states()

        # Outside the logger check on purpose: -2 is how a peer learns this minion is
        # gone, so gating it on a logger being attached meant a minion that died before
        # its logger was up stayed 'alive' to everyone else forever (B2).
        try:
            self.status = -2
        except Exception:
            self.log(logging.WARNING, f"Could not mark {self.name} as terminated:\n{traceback.format_exc()}")

        for i in list(self._queue.keys()):
            self.disconnect(i)

        bv: SharedBuffer
        for bk, bv in self._shared_buffer.items():
            bv.terminate()
        self._shared_dict.terminate()

        # Unlinking rather than merely closing, and with no wait for a peer to let go --
        # same reasoning as SharedNdarray.terminate() (C9): a peer still holding this
        # segment open after we unlink is normal, not an error, and the OS reclaims it
        # when that peer closes. A peer's next `heartbeat_of()` then gets FileNotFoundError
        # on any handle it opens after this point, which is the clean-exit signal
        # `heartbeat_of`'s docstring distinguishes from a frozen-but-present counter.
        if self._heartbeat_ctx is not None:
            try:
                self._heartbeat_ctx.__exit__(None, None, None)
            except Exception:
                pass
        if self._heartbeat_shm is not None:
            try:
                self._heartbeat_shm.close()
            except Exception:
                pass
            try:
                self._heartbeat_shm.unlink()
            except FileNotFoundError:
                pass
            except Exception:
                self.log(logging.WARNING,
                        f"Failed to unlink {self.name}'s heartbeat segment:\n{traceback.format_exc()}")

        # if self.Process._popen:
        #     self.Process.join()  # _popen is a protected attribute. Maybe test with .is_alive()?

        if self.Process.is_alive():
            self.Process.close()

    def watch_state(self, name, val):
        """Edge-detect a change in `val` for `name` since the last call; the first call for a given `name` always reports a change.

        Keys are caller-chosen and unrelated to shared state names -- see
        `AbstractMinionMixin.watch_state`'s `COMPILER_WATCH_PREFIX` for how a
        compiler keeps its own watch keys from colliding with the minion's.
        """
        if name not in self._watching_state.keys():
            self._watching_state[name] = val
            return True
        else:
            changed = val != self._watching_state[name]
            self._watching_state[name] = val
            return changed


class MinionLogHandler:
    """
    A simple handler for logging events. It runs in the listener core and
    dispatches events to loggers based on the name in the received record,
    which then get dispatched, by the logging system, to the handlers
    configured for those loggers.
    """

    def handle(self, record):
        """Dispatch a log record received from a worker process to the matching local logger.

        Runs in the listener process (see `innerLoop`'s use of a `QueueHandler` in
        every other process): records cross a `multiprocessing.Queue` from
        whichever minion emitted them and are re-dispatched here as if logged
        locally, with `processName` annotated to show both the listener and the
        original process.
        """
        if record.name == "root":
            logger = logging.getLogger()
        else:
            logger = logging.getLogger(record.name)
        if logger.isEnabledFor(record.levelno):
            record.processName = '%s (for %s)' % (mp.current_process().name, record.processName)
            logger.handle(record)


class TimerMinion(BaseMinion):
    """A BaseMinion that fires one or more named, independently-timed callbacks from its own tick loop.

    Each named timer tracks its own interval and last-fired elapsed time in
    `self.timer`; `exec` (driven by `main`, so once per tick) checks every timer
    against `_interval` and invokes its registered callback when due. A single
    shared `_interval` applies to all timers -- there is no per-timer interval --
    so this is meant for callbacks that all want roughly the same polling rate,
    not a general scheduler.
    """

    def __init__(self, name, refresh_interval=10):
        """Set up the 'default' timer/callback and convert `refresh_interval` (ms) to the internal seconds interval."""
        super(TimerMinion, self).__init__(name)
        self.timer = {'default': [-1, -1]}  # 1. interval, 2. elapsed time, 3. init_time
        self.timer_cb_func = {'default': self.on_time}
        self._isrunning = False
        self._interval = refresh_interval / 1000

    @property
    def refresh_interval(self):
        """The polling interval shared by every timer, in milliseconds."""
        return self._interval * 1000

    @refresh_interval.setter
    def refresh_interval(self, val):
        """Set the polling interval shared by every timer, given in milliseconds."""
        self._interval = val / 1000

    def add_timer(self, name, cb_func=None):
        '''
        allows to add custom timer
        :param name: timer's name
        :return:
        '''
        self.timer[name] = [-1, -1]
        self.timer_cb_func[name] = cb_func

    def add_callback(self, timer_name, cb_func):
        """Register or replace the callback fired when `timer_name`'s interval elapses; warns (but proceeds) when replacing an existing one, errors for an unknown timer."""
        if timer_name in self.timer_cb_func.keys():
            if self.timer_cb_func.get(timer_name) is not None:
                self.warning(f'Reset the callback function of the ["{timer_name}"] timer')
            self.timer_cb_func[timer_name] = cb_func
        else:
            self.error(f'NameError: Unknown timer name: {timer_name}')

    def start_timing(self, timer_name='default'):
        """(Re)arm one timer, a list of them, or every timer (`'all'`), resetting its elapsed time to 0 from now."""
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
        """Freeze one timer, a list of them, or every timer (`'all'`), storing its final elapsed time and marking it as stopped (init_time -1)."""
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
        """Fire the callback for every running timer whose interval has elapsed since it last fired.

        Called once per tick from `main`; a stopped timer (init_time < 0, per
        `stop_timing`) is silently skipped rather than treated as due.
        """
        cur_time = perf_counter()
        for k, v in self.timer.items():
            if v[1] >= 0:
                elapsed = cur_time - v[1]
                if elapsed - v[0] > self._interval:
                    v[0] = elapsed
                    cb_func = self.timer_cb_func.get(k)
                    if cb_func is not None:
                        cb_func(v[0])

    def get_time(self, timer_name='default'):
        """Return one timer's `[elapsed, init_time]`, a list of them, or every timer's (`'all'`), updating `elapsed` as a side effect if the interval has passed but never firing the callback (unlike `exec`)."""
        cur_time = perf_counter()
        if type(timer_name) is str:
            if timer_name == 'all':
                tmp_times = []
                for k, v in self.timer.items():
                    elapsed = cur_time - v[1]
                    if elapsed - v[0] > self._interval:
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
        """Arm the 'default' timer; called by `innerLoop` on entering the running state."""
        self.start_timing('default')

    def main(self):
        """Poll every timer for due callbacks once per tick."""
        self.exec()

    @property
    def elapsed(self):
        """The 'default' timer's current elapsed time, in seconds."""
        return self.get_time('default')[1]

    def on_time(self, t):
        """Default callback for the 'default' timer; override or replace via `add_callback` to act on each tick. No-op by default."""
        pass


class AbstractMinionMixin:
    '''
    This class should serve as an compiler between Qt window and minion core handler,
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

    def debug(self, msg):
        """Log `msg` at DEBUG level through the wrapped minion."""
        self._processHandler.debug(msg)

    def info(self, msg):
        """Log `msg` at INFO level through the wrapped minion."""
        self._processHandler.info(msg)

    def warning(self, msg):
        """Log `msg` at WARNING level through the wrapped minion."""
        self._processHandler.warning(msg)

    def error(self, msg):
        """Log `msg` at ERROR level through the wrapped minion."""
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
        """Fetch one message from `source` and dispatch it to `parse_msg`; logs but does not dispatch an empty receive."""
        msg, msg_type = self._processHandler.get(source)
        if msg is not None:
            if msg_type is not None:
                self.log("DEBUG", f"Received message from [{source}] (type: {msg_type})")
            else:
                self.log("DEBUG", f"Received message from [{source}] (type: UNKNOWN)")
            self.parse_msg(msg_type, msg)
        else:
            self.log("DEBUG", f"EMPTY MESSAGE from [{source}]")

    def get_nowait(self, source: str):
        """Parse one queued message, returning silently when no message exists."""
        msg, msg_type = self._processHandler.get_nowait(source)
        if msg is not None:
            self.parse_msg(msg_type, msg)
            return True
        return False

    def get_linked_minion_names(self):
        """Names of every minion currently linked to the wrapped minion."""
        return list(self._processHandler._linked_minion.keys())

    def get_shared_state_names(self, minion_name):
        """Names of every shared state exposed by `minion_name`."""
        return list(self._processHandler.get_shared_state_names(minion_name))

    def create_state(self, state_name, state_val, use_buffer=False, dtype=None):
        """Declare a new shared state on the wrapped minion; see `BaseMinion.create_state`."""
        self._processHandler.create_state(state_name, state_val, use_buffer, dtype)

    def remove_state(self, state_name):
        """Delete a shared state from the wrapped minion."""
        self._processHandler.remove_state(state_name)

    def set_state(self, state_name, state_val):
        """Write a state on the wrapped minion; see `BaseMinion.set_state`."""
        self._processHandler.set_state(state_name, state_val)

    def set_state_to(self, minion_name, state_name, state_val):
        """Write a state on `minion_name` (self or a linked peer); see `BaseMinion.set_state_to`."""
        self._processHandler.set_state_to(minion_name, state_name, state_val)

    def get_state(self, state_name):
        """Read a state from the wrapped minion's own SharedDict."""
        return self._processHandler.get_state(state_name)

    def get_state_from(self, minion_name, state_name):
        """Read a state from `minion_name` (self or a linked peer); see `BaseMinion.get_state_from`."""
        return self._processHandler.get_state_from(minion_name, state_name)

    def create_shared_buffer(self, buffer_name, buffer_val):
        """Back a new state on the wrapped minion with a shared buffer; see `BaseMinion.create_shared_buffer`."""
        self._processHandler.create_shared_buffer(buffer_name, buffer_val)

    def remove_shared_buffer(self, buffer_name):
        """Remove a shared buffer from the wrapped minion."""
        self._processHandler.remove_shared_buffer(buffer_name)

    def has_foreign_state(self, minion_name, buffer_name):
        """Whether a linked peer currently has the named state."""
        return self._processHandler.has_foreign_state(minion_name, buffer_name)

    def has_state(self, buffer_name):
        """Whether the wrapped minion currently has the named state."""
        return self._processHandler.has_state(buffer_name)

    def parse_msg(self, msg_type, msg):
        """Subclass hook: interpret one message dispatched by `get`/`get_nowait`. No-op by default."""
        pass

    def watch_state(self, name, val):
        """Edge-detect a change in `val` for `name`, namespaced under COMPILER_WATCH_PREFIX so a compiler's watch keys can't collide with the minion's own."""
        return self._processHandler.watch_state(_contract.COMPILER_WATCH_PREFIX + name, val)

    def shutdown(self):
        """Request the wrapped minion's graceful shutdown."""
        self._processHandler.shutdown()

    def status(self):
        """The wrapped minion's current status value."""
        return self._processHandler.status


class TimerMinionMixin(AbstractMinionMixin):
    """AbstractMinionMixin variant for compilers wrapping a `TimerMinion`, exposing its named-timer API."""

    def has_timer(self, name):
        """Whether the wrapped TimerMinion has a timer named `name`."""
        self._processHandler: TimerMinion
        return name in self._processHandler.timer.keys()

    def add_timer(self, name, cb_func=None):
        """Add a new named timer on the wrapped TimerMinion."""
        self._processHandler.add_timer(name, cb_func)

    def start_timing(self, timer_name='default'):
        """(Re)arm one, several, or all of the wrapped TimerMinion's timers."""
        self._processHandler.start_timing(timer_name)

    def stop_timing(self, timer_name='default'):
        """Freeze one, several, or all of the wrapped TimerMinion's timers."""
        self._processHandler.stop_timing(timer_name)

    def get_time(self, timer_name='default'):
        """Read one, several, or all of the wrapped TimerMinion's timer states."""
        return self._processHandler.get_time(timer_name)

    def elapsed(self):
        """The wrapped TimerMinion's 'default' timer elapsed time."""
        return self._processHandler.elapsed

    def timerInterval(self):
        """The wrapped TimerMinion's shared polling interval, in milliseconds."""
        self._processHandler: TimerMinion
        return self._processHandler.refresh_interval

    def setTimerInterval(self, val):
        """Set the wrapped TimerMinion's polling interval, in milliseconds.

        Goes through the `refresh_interval` property, which is what `TimerMinion`
        actually reads: it owns the ms-to-seconds conversion into `_interval`, so
        assigning the raw attribute instead would silently do nothing.
        """
        self._processHandler.refresh_interval = val
