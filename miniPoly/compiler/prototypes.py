import csv
import os
import time

import cv2

from miniPoly.core.minion import TimerMinionMixin, TimerMinion

import traceback
# Underscore alias keeps `contract` out of this module's public namespace.
from miniPoly.core import contract as _contract

class AbstractCompiler(TimerMinionMixin):
    """Base contract every compiler shell (graphics, camera, serial) is built against.

    Wraps the process-handler minion (`processHandler`) that owns the shared-memory segment
    and the timer loop: `__init__` registers this instance's tick handler with it, and
    `on_time`/`on_close`/`on_protocol` are the hooks a subclass overrides to add its own
    per-tick work, teardown and (currently uncalled) protocol-tick logic. The base
    implementations are all no-ops, so a minimal compiler needs to override nothing.
    """

    _processHandler: TimerMinion

    def __init__(self, processHandler: TimerMinion):
        """Register this compiler's tick callback with its owning process handler.

        Subclasses call this (directly or via `super().__init__`) before touching any
        minion state, since `_processHandler.add_callback` is what makes `_on_time` -- and
        therefore `on_time` -- run at all; nothing here creates shared memory or state.
        """
        super().__init__()
        self._processHandler = processHandler
        self._processHandler.add_callback('default', self._on_time)
        self.refresh_interval = self._processHandler.refresh_interval
        self.name = self._processHandler.name

    def _on_time(self, t):
        """Per-tick callback registered with the process handler; runs on_time/on_close guarded.

        Runs on every tick of `_processHandler`'s timer. Checks `status()` first so a status
        that has already dropped to zero or below triggers `_on_close()` before `on_time`
        runs one more time. `on_time` and the process handler's own `on_time` are each
        wrapped in their own try/except: letting either exception escape here would
        propagate out of the timer callback and kill this minion outright, while it kept
        reporting itself alive to every peer still watching its heartbeat (see the inline
        B2 note below).
        """
        if self.status() <= 0:
            self._on_close()
        try:
            self.on_time(t)
        except:
            self.error('Error in on_time')
            self.error(traceback.format_exc())
        # Guarded for the same reason as the compiler's own on_time: this call sat
        # outside the try block, so an exception raised by the process shell's on_time
        # propagated out of the callback and killed the minion, which then went on
        # looking alive to all its peers (B2).
        try:
            self._processHandler.on_time(t)
        except:
            self.error('Error in the process handler on_time')
            self.error(traceback.format_exc())

    def on_time(self, t):
        """Per-tick hook; no-op by default, overridden by every concrete compiler.

        Called once per tick, from `_on_time`, already inside a try/except -- an override
        does not need to guard against its own exceptions escaping into the timer loop.
        """
        pass

    def on_protocol(self, t):
        """Per-protocol-tick hook; no-op by default.

        Distinct from `on_time`: nothing in this file or in graphics.py/cameras.py/
        serial_devices.py currently calls `on_protocol`, so it exists as a base-contract
        entry point with no live caller yet.
        """
        pass

    def _on_close(self):
        """Mark this minion's framework status as stopped, then run the subclass's teardown.

        Called by `_on_time` once `status()` drops to zero or below. Sets FRAMEWORK_STATUS
        to -1 before calling `on_close()`, so any peer polling this minion's status already
        sees it shutting down while the subclass is still closing files/devices.
        """
        self.set_state(_contract.FRAMEWORK_STATUS, -1)
        self.on_close()

    def on_close(self):
        """Teardown hook; no-op by default, overridden by subclasses that own resources.

        Called once, by `_on_close`, after FRAMEWORK_STATUS has already been set to -1 -- so
        an override should not rely on `status()` still reading positive.
        """
        pass


class StreamingCompiler(AbstractCompiler):
    """A compiler that can log its shared/local state and buffers to disk on a trigger signal.

    Adds three things on top of AbstractCompiler: a streaming lifecycle (see
    `_streaming_setup`/`_prepare_streaming`/`_start_streaming`/`_stop_streaming`/
    `_streaming`) gated by a foreign minion's STREAM_ENABLE state; a registry of "streaming
    states" and "streaming buffers" written to a CSV row / binary or movie file once per
    tick when they change; and a protocol table (loaded by subclasses such as
    ShaderStreamer) that can drive those states over time. `timer_minion` supplies the
    shared timestamp used to timestamp every streamed row; `trigger_minion` is where
    StreamToDisk/SaveDir/SaveName and protocol control states are read from.
    """

    def __init__(self, *args, timer_minion=None, trigger_minion=None, **kwargs):
        '''
        A compiler for the IOHandler class that receives and save all data from its connected minions.
        :param timer_minion: name of the minion that generates timestamps
        :param trigger_minion: the name of a foreign minion whose state "StreamToDisk" will trigger the streaming
        '''
        super().__init__(*args, **kwargs)

        self._timer_minion = timer_minion
        self._trigger_minion = trigger_minion
        self.trigger = None

        # Initializing saving handler
        self._state_stream_fn = None
        self._state_stream_handler = None
        self._state_stream_writer = None
        self._buffer_handle_param = {}
        self._buffer_streaming_handle = {}
        self._streaming_start_time = 0
        self.streaming = False

        self._streaming_states = {}
        self._streaming_buffers = {}
        self._shared_states = []
        self._shared_buffers = []

        self._last_row = []

        # Initializing saving parameters and create the corresponding shared state to receive GUI control
        self.saving_param = {'StreamToDisk': False,
                             'SaveDir': None,
                             'SaveName': None}

        # for k, v in self.saving_param.items():
        #     self.create_state(k, v)

    # ------------------------------------------------------------------
    # Public read-only views.
    #
    # Background: the downstream CaImg_App currently reaches into underscore
    # attributes of this class and its subclasses in 447 places, which means
    # miniPoly has no stable API surface -- any internal rename breaks the app.
    # The properties below cover the six most frequently used ones (233 sites,
    # about 52%).
    #
    # The underscore names are all kept, so existing code is unaffected;
    # **new code should use the public names**.
    # Values are fetched with getattr rather than initialised in __init__ so that
    # subclasses with no protocol concept at all (OMSDuo, ScanListener) do not
    # gain attributes they never had.
    # ------------------------------------------------------------------

    @property
    def timer_minion(self):
        """str | None: name of the minion providing the `timestamp` state."""
        return self._timer_minion

    @property
    def trigger_minion(self):
        """str | None: name of the minion providing streaming and protocol control states."""
        return self._trigger_minion

    @property
    def protocol(self):
        """pandas.DataFrame | None: the loaded protocol table, or None."""
        return getattr(self, '_protocol', None)

    @property
    def protocol_start_time(self):
        """float | None: protocol start time in seconds, or None when not running."""
        return getattr(self, '_protocol_start_time', None)

    @property
    def protocol_time_index(self):
        """numpy.ndarray | None: the protocol time column, used to locate cmd_idx."""
        return getattr(self, '_time_index_col', None)

    @property
    def running_time(self):
        """float: protocol elapsed time in seconds; 0 when not running."""
        return getattr(self, '_running_time', 0)

    def create_streaming_state(self, state_name, val, shared=False, use_buffer=False, dtype=None):
        """Register a local (and optionally shared) state to include in the streaming CSV rows.

        Errors instead of overwriting when `state_name` is already registered, since a
        silent overwrite would drop whichever registration owned the name first. When
        `shared=True` this also calls `create_state`, so the name becomes visible to peers
        through the usual shared-state mechanism, not just to `_streaming()`'s own
        bookkeeping.
        """
        if state_name in self._streaming_states:
            self.error('{} is already in the streaming state list'.format(state_name))
        else:
            self._streaming_states[state_name] = val
            if shared:
                self.create_state(state_name, val, use_buffer=use_buffer, dtype=dtype)
                self._shared_states.append(state_name)
                self.info('Created shared streaming state [{}]'.format(state_name))
            else:
                self.info('Created local streaming state [{}]'.format(state_name))

    def remove_streaming_state(self, mi_name, state_name):
        """Undo `create_streaming_state`, releasing the shared state too if there was one.

        `mi_name` is used only in the log messages; removal itself is keyed on `state_name`
        alone, since a compiler only ever manages its own streaming-state registry. A no-op
        aside from the error log when `state_name` was never registered.
        """
        if state_name in self._streaming_states:
            del self._streaming_states[state_name]
            if state_name in self._shared_states:
                self._shared_states.remove(state_name)
                self.remove_state(state_name)
            self.info('Removed {} from the streaming state list of {}'.format(state_name, mi_name))
        else:
            self.error('{} is not registered for streaming'.format(mi_name))

    def create_streaming_buffer(self, buffer_name, buffer_val, saving_opt=None, shared=False):
        """Register a local (and optionally shared) buffer to write to a per-file stream on disk.

        `saving_opt` selects the on-disk format ('binary'/'movie'/anything else disables
        saving that buffer, see `_prepare_streaming`) and is stored alongside the buffer
        value rather than passed again at streaming time. Errors instead of overwriting when
        `buffer_name` is already registered, mirroring `create_streaming_state`.
        """
        if buffer_name in self._streaming_buffers:
            self.error('{} is already in the streaming buffer list'.format(buffer_name))
        else:
            self._streaming_buffers[buffer_name] = [buffer_val, saving_opt]
            if shared:
                self._shared_buffers.append(buffer_name)
                self.create_shared_buffer(buffer_name, buffer_val)
                self.info('Created shared streaming buffer [{}]'.format(buffer_name))
            else:
                self.info('Created local streaming buffer [{}]'.format(buffer_name))

    def remove_streaming_buffer(self, buffer_name):
        """Undo `create_streaming_buffer`, releasing the shared buffer too if there was one.

        A no-op aside from the error log when `buffer_name` was never registered.
        """
        if buffer_name in self._streaming_buffers.keys():
            del self._streaming_buffers[buffer_name]
            if buffer_name in self._shared_buffers:
                self.remove_shared_buffer(buffer_name)
                self._shared_buffers.remove(buffer_name)
            self.info('Removed {} from the streaming buffer list'.format(buffer_name))
        else:
            self.error('Cannot remove {} as it is not registered for streaming'.format(buffer_name))

    def get_streaming_state(self, state_name):
        """Return the current value of a registered streaming state, refreshing it if shared.

        A shared state is re-read from shared memory on every call (`get_state`) rather than
        returned from the local cache, since a peer can update it between ticks; a
        local-only state is simply returned as already held.
        """
        if state_name in self._streaming_states.keys():
            if state_name in self._shared_states:
                self._streaming_states[state_name] = self.get_state(state_name)
            return self._streaming_states[state_name]
        else:
            self.error('{} is not registered for streaming'.format(state_name))
            return None

    def set_streaming_state(self, state_name, val):
        """Write a value into a registered streaming state, through shared memory if shared.

        Mirrors `get_streaming_state`: a shared state is written through `set_state` so
        peers see it, a local one is simply overwritten in `_streaming_states`.
        """
        if state_name in self._streaming_states.keys():
            if state_name in self._shared_states:
                self.set_state(state_name, val)
            else:
                self._streaming_states[state_name] = val
        else:
            self.error('{} is not registered for streaming'.format(state_name))

    def get_streaming_buffer(self, buffer_name):
        """Return the current value of a registered streaming buffer, refreshing it if shared.

        Refreshes only `[0]` (the buffer array) from shared memory; `[1]` (the saving
        option) is fixed at registration. Per the comment on `set_streaming_buffer`, this
        getter currently has no caller anywhere in the codebase -- shared buffers are
        written by `set_streaming_buffer` and read back for streaming by `_streaming()`
        directly from `_streaming_buffers`.
        """
        if buffer_name in self._streaming_buffers.keys():
            if buffer_name in self._shared_buffers:
                self._streaming_buffers[buffer_name][0] = self.get_state(buffer_name)
            return self._streaming_buffers[buffer_name]
        else:
            self.error('{} is not registered for streaming'.format(buffer_name))
            return None

    def set_streaming_buffer(self, buffer_name, val):
        """Write a value into a registered streaming buffer, through shared memory if shared.

        The local copy is always updated so `_streaming()` -- which writes
        `_streaming_buffers[name][0]` straight to disk -- sees the new frame; the
        shared-memory write is an additional side effect for shared buffers, not a
        substitute for the local update (see the A1 note below).
        """
        # The local copy is updated unconditionally. When the buffer was shared this
        # wrote only the shared state, while `_streaming()` writes `v[0]` -- the local
        # copy -- straight to disk, so a shared streaming buffer recorded its very first
        # frame over and over for the whole session (A1). The only function that would
        # have refreshed the local copy, `get_streaming_buffer()`, is called nowhere in
        # either repository.
        if buffer_name in self._streaming_buffers.keys():
            self._streaming_buffers[buffer_name][0] = val
            if buffer_name in self._shared_buffers:
                self.set_state(buffer_name, val)
        else:
            self.error('{} is not registered for streaming'.format(buffer_name))

    def _streaming_setup(self):
        """Start or stop file streaming when the trigger minion's STREAM_ENABLE flag flips.

        Called once per tick from `on_time`. Streaming is gated by `should_stream()` so a
        compiler that opts out (e.g. a camera not selected in the GUI) never opens or closes
        files even while STREAM_ENABLE is on for the rig as a whole. `watch_state` is what
        detects the edge -- this runs `_prepare_streaming`/`_start_streaming` or
        `_stop_streaming` only on the tick the flag actually changes, not on every tick it
        happens to already be True.
        """
        is_streaming = self.get_state_from(self._trigger_minion, _contract.STREAM_ENABLE)
        if self.should_stream():  # check if the compiler should be involved in streaming
            if self.watch_state(_contract.STREAM_ENABLE, is_streaming):  # Triggered at the onset and the end of streaming
                if is_streaming:
                    err = self._prepare_streaming()
                    if not err:
                        self._start_streaming()
                else:  # close all files before streaming stops
                    self._stop_streaming()

    def should_stream(self):
        """Whether this compiler should participate in streaming at all; True by default.

        Overridden by compilers that stream only conditionally -- e.g.
        `AbstractCameraCompiler` checks whether its device was selected in the GUI's device
        list -- to opt out of `_streaming_setup` entirely regardless of the global
        STREAM_ENABLE flag.
        """
        return True

    def _prepare_streaming(self):
        """Validate save location/filenames and stage the paths `_start_streaming` will open.

        Called once, right before `_start_streaming`, when STREAM_ENABLE turns on. Returns
        True on any failure (undefined SaveDir/SaveName, a missing save directory, or a
        state/buffer file that already exists) and logs the reason, so `_streaming_setup`
        can skip `_start_streaming` rather than clobbering an existing file or crashing on an
        `open()` of a bad path. On success it only stashes `_state_stream_fn`/
        `_buffer_handle_param`; no files are created yet.
        """
        err = False
        stateStreamHandlerFn = None
        bufferHandlerParam = {}

        save_dir = self.get_state_from(self._trigger_minion, _contract.STREAM_DIR)
        # The None check has to come before the concatenation (B9): a None SaveName used
        # to reach `+ "_" + self.name` first, losing the "undefined parameter" message to
        # a bare TypeError.
        stream_name = self.get_state_from(self._trigger_minion, _contract.STREAM_NAME)
        file_name = None if stream_name is None else f"{stream_name}_{self.name}"
        missing_saving_param = [i for i in [save_dir, file_name] if i is None]
        if len(missing_saving_param) > 0:
            err = True
            self.error("Streaming could not start because of the following undefined parameter(s): {}".format(
                missing_saving_param))

        # Check if the save directory exists and any file with the same name already exists
        if not err:
            if os.path.isdir(save_dir):
                stateStreamHandlerFn = os.path.join(save_dir, f"{file_name}.csv")
                if os.path.isfile(stateStreamHandlerFn):
                    err = True
                    self.error("Streaming could not start because the state csv file {} already exists".format(
                        stateStreamHandlerFn))

                errFnList = []
                for buf_name, v in self._streaming_buffers.items():
                    bufferHandlerParam[buf_name] = {}
                    if v[1] is None or v[1] == 'binary':
                        BIN_Fn = os.path.join(save_dir, f"{file_name}_{self.name}_{buf_name}.bin")
                        if os.path.isfile(BIN_Fn):
                            errFnList.append(f"{file_name}_{self.name}_{buf_name}.bin")
                            err = True
                        else:
                            bufferHandlerParam[buf_name]['type'] = 'binary'
                            bufferHandlerParam[buf_name]['fn'] = BIN_Fn
                    elif v[1] == 'movie':
                        BIN_Fn = os.path.join(save_dir, f"{file_name}_{self.name}_{buf_name}.avi")
                        if os.path.isfile(BIN_Fn):
                            errFnList.append(f"{file_name}_{self.name}_{buf_name}.avi")
                            err = True
                        else:
                            bufferHandlerParam[buf_name]['type'] = 'movie'
                            bufferHandlerParam[buf_name]['fn'] = BIN_Fn
                    else:
                        bufferHandlerParam[buf_name]['type'] = 'disabled'
                        bufferHandlerParam[buf_name]['fn'] = None
                        self.warning("Unknown streaming format: [{}];  Streaming of {} from {} is disabled".format(v[1],
                                                                                                                   buf_name,
                                                                                                                   self.name))
                    bufferHandlerParam[buf_name]['shape'] = v[0].shape[:-1]

                if len(errFnList) > 0:
                    self.error("Streaming could not start because the following buffer files already exist: {}".format(
                        errFnList))
                    err = True
            else:
                err = True
                self.error("Streaming could not start because the save directory {} does not exist".format(save_dir))

        if not err:
            self._state_stream_fn = stateStreamHandlerFn
            self._buffer_handle_param = bufferHandlerParam

        return err

    def _start_streaming(self):
        """Open the state CSV and buffer files staged by `_prepare_streaming`, and write row zero.

        Called once, immediately after a successful `_prepare_streaming`. Writes the CSV
        header and an initial (t=0) row unconditionally, seeds `_last_row` from that first
        row so `_streaming`'s change-detection compares like-for-like from the first real
        tick, and only then flips `self.streaming` to True -- so `_streaming()` cannot run
        against half-open file handles.
        """
        # reset buffered state
        # Create the state csv file
        self._state_stream_handler = open(self._state_stream_fn, 'w', newline='')
        self._state_stream_writer = csv.writer(self._state_stream_handler)
        name_row = ['Time']
        for state_name in self._streaming_states:
            name_row.append(f"{self.name}_{state_name}")
            self.watch_state(state_name, None)
        self._state_stream_writer.writerow(name_row)
        val_row = [0]
        for state_name in self._streaming_states:
            state_val = self.get_streaming_state(state_name)
            val_row.append(state_val)
        # Sliced the same way `_streaming()` compares (B7): `_last_row` used to keep the
        # leading timestamp `val_row` has and `_streaming()` doesn't, so the very first
        # comparison after streaming starts compared lists of different lengths and was
        # always unequal. Harmless on its own -- the first row streams either way -- but
        # it masked this exact mismatch for anyone touching the comparison later.
        self._last_row = val_row[1:]
        self._state_stream_writer.writerow(val_row)
        self._state_stream_handler.flush()

        # Create the buffer files
        for buf_name, v in self._streaming_buffers.items():
            fn = self._buffer_handle_param[buf_name]['fn']
            fshape = self._buffer_handle_param[buf_name]['shape']
            if v[1] is None or v[1] == 'binary':
                self._buffer_streaming_handle[buf_name] = (open(fn, 'wb'), v[1])
            elif v[1] == 'movie':
                self._buffer_streaming_handle[buf_name] = (cv2.VideoWriter(fn, cv2.VideoWriter_fourcc(*'MJPG'),
                                                                           int(1000 / self.refresh_interval),
                                                                           (fshape[1], fshape[0])), 'movie')
            else:
                self._buffer_streaming_handle[buf_name] = (None, None)

        self._streaming_start_time = self.get_timestamp()
        self.streaming = True

    def _stop_streaming(self):
        """Close all open streaming file handles and reset streaming state back to idle.

        Called once when STREAM_ENABLE turns off. Guarded by `if self.streaming` so it is
        safe to call speculatively; `_streaming_setup` only calls it on the falling edge, but
        nothing else about this method assumes that.
        """
        if self.streaming:
            self.streaming = False
            self._state_stream_handler.close()

            for buf_name, v in self._buffer_streaming_handle.items():
                if v[1] is None or v[1] == 'binary':
                    v[0].close()
                elif v[1] == 'movie':
                    v[0].release()
                else:
                    pass

            self._state_stream_fn = None
            self._state_stream_handler = None
            self._state_stream_writer = None
            self._buffer_handle_param = {}
            self._buffer_streaming_handle = {}
            self._streaming_start_time = 0
            self.streaming = False

    def _streaming(self):
        """Append one row to the state CSV, and one frame per buffer file, if anything changed.

        Called every tick from `on_time` while `self.streaming` is True. A row is written
        only when the streaming states differ from `_last_row` -- so an unchanging protocol
        produces a sparse CSV rather than one row per tick -- and the buffer files are
        appended in lockstep with that same row, keyed to the same tick rather than sampled
        independently.
        """
        if self.streaming:
            t = self.get_timestamp() - self._streaming_start_time
            val_row = [t]
            state_changed = False
            for state_name in self._streaming_states:
                state_val = self.get_streaming_state(state_name)
                val_row.append(state_val)

            if val_row[1:] != self._last_row:
                self._state_stream_writer.writerow(val_row)
                self._last_row = val_row[1:]
                for buf_name, v in self._streaming_buffers.items():
                    if v[1] is None or v[1] == 'binary':
                        self._buffer_streaming_handle[buf_name][0].write(bytearray(v[0]))
                    elif v[1] == 'movie':
                        self._buffer_streaming_handle[buf_name][0].write(v[0].repeat(3,axis=2))
                    else:
                        pass

    def get_timestamp(self):
        """Return the current time in seconds, from the configured timer minion or the local clock.

        Falls back to `time.perf_counter()` when no `timer_minion` was configured, so a
        compiler with no shared timer still gets a monotonically increasing timestamp for
        its own streamed rows -- just not one comparable across processes.
        """
        # An empty string counts as "no timer minion", not as a minion named ''. Testing
        # only `is not None` meant a caller that passed timer_minion='' fell into
        # get_state_from('') and got None back; dynamixel.py carried a copy of this whole
        # method purely to add the second test (A3).
        if self._timer_minion is not None and self._timer_minion != '':
            if self._timer_minion != self.name:
                return self.get_state_from(self._timer_minion, _contract.TIMER_TIMESTAMP) / 1000
            else:
                return self.get_state(_contract.TIMER_TIMESTAMP) / 1000
        else:
            return time.perf_counter()

    def on_time(self, t):
        """Per-tick hook: run the streaming trigger check, then append a row if streaming.

        Overrides `AbstractCompiler.on_time`; unlike the no-op base, every StreamingCompiler
        subclass needs this pair of calls, so it is not left for each subclass to remember --
        a subclass that overrides `on_time` again (e.g. ShaderStreamer,
        AbstractCameraCompiler) calls `super().on_time(t)` to keep it.
        """
        self._streaming_setup()
        self._streaming()
