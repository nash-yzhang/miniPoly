"""What the framework does when something goes wrong.

Every check here pins one guarantee introduced by roadmap Stage 1 (see
docs/PROJECT_OVERVIEW.md section 6). They belong together because they share a theme rather
than a module: none of them is about the happy path. A crash, a peer that never came up,
a window that has not been shown yet, an idle queue, a value the codec cannot represent
-- the framework used to respond to each of these by hanging, by lying to its peers, or
by burning a core.

Each check was verified to fail against the pre-fix code, which is the only thing that
distinguishes a real regression test from a permanent green light.

Most checks drive the method under test with a stub `self` (`types.SimpleNamespace`
plus the handful of attributes the method touches) instead of building a live minion.
That is deliberate: `StreamingCompiler`, `AbstractGUIAPP` and `LoggerMinion` all need a
running process, a Qt application or a shared-memory namespace before they can be
constructed, and none of that is what these particular fixes are about. The one check
that genuinely needs two processes -- "does a crashed minion tell its peers it died" --
spawns them.

Standalone:  python tests/test_failure_paths.py
pytest:      pytest tests/test_failure_paths.py
"""

import multiprocessing as mp
import sys
import traceback
import types
import warnings
from multiprocessing import shared_memory
from time import perf_counter, sleep

import numpy as np

from miniPoly.core import contract
from miniPoly.core.buffer import SharedDict, SharedNdarray
from miniPoly.core.minion import BaseMinion, TimerMinion, SHAREDLOCK

JOIN_TIMEOUT = 20.0

# Number of main() ticks before the crashing minion raises. Large enough that the parent
# can attach to its status segment first, small enough to keep the check quick.
TICKS_BEFORE_CRASH = 20


# --------------------------------------------------------------------------
# workers (module level so Windows spawn can import them)
# --------------------------------------------------------------------------

class _CrashAfterSomeTicks(BaseMinion):
    """Raises from main() once its peers have had time to attach."""

    def initialize(self):
        self._ticks = 0

    def main(self):
        self._ticks += 1
        if self._ticks >= TICKS_BEFORE_CRASH:
            raise RuntimeError("deliberate failure inside main()")


class _BusyMinion(TimerMinion):
    """A minion that just spins, so a peer can time how fast it reacts to a kill."""

    def on_time(self, t):
        pass


class _TicksNormally(TimerMinion):
    """The positive control for the heartbeat check: nothing unusual happens."""

    def on_time(self, t):
        pass


#: How long `_DeclaresLate` stays inside initialize() before creating its state. Stands in
#: for a real compiler's __init__ -- DynamotorGUI took 3.2 s in the session log behind B11.
DECLARE_DELAY = 0.3
#: And how much longer it stays there afterwards, so the seal lands well after the state
#: does. Without this gap a reader could break out on the seal instead of on the value, and
#: the check would no longer pin the per-attempt `err_code` reset.
SEAL_DELAY = 1.5
LATE_STATE = "arrives_late"
LATE_VALUE = 7


class _SealsImmediately(TimerMinion):
    """Declares nothing of its own, so initialize() returns -- and it seals -- at once."""

    def on_time(self, t):
        pass


class _DeclaresLate(TimerMinion):
    """Declares one state part-way through initialize(), and seals well after that."""

    def initialize(self):
        super().initialize()
        sleep(DECLARE_DELAY)
        self.create_state(LATE_STATE, LATE_VALUE)
        sleep(SEAL_DELAY)

    def on_time(self, t):
        pass


class _HangsInsideOnTime(TimerMinion):
    """Hangs forever on its first callback -- `status` never changes after that."""

    def initialize(self):
        super().initialize()
        self._hung = False

    def on_time(self, t):
        if not self._hung:
            self._hung = True
            while True:  # deliberate, permanent hang
                pass


# --------------------------------------------------------------------------
# checks
# --------------------------------------------------------------------------

def check_crashed_minion_reports_its_death():
    """A minion that dies of an unhandled exception must tell its peers (B2).

    The peer here is the parent process holding a handle on the crashing minion's status
    segment, which is exactly how `is_minion_alive()` observes a peer. `innerLoop` now
    guards the whole loop and runs `_shutdown()` from a `finally`, and `_shutdown()` sets
    the status to -2 regardless of whether a logger was ever attached.

    Before the fix the exception propagated straight out of `innerLoop`: the child exited
    1, `_shutdown()` never ran, and the status segment kept reporting the last value the
    child wrote -- 1, meaning alive. Every peer polling it therefore saw a live minion
    forever, and `AbstractGUIAPP.shutdown()` waited for it forever.
    """
    problems = []
    name = "FP_CRASH"
    # An aborted earlier run can leave these behind, and then prepare_shared_buffer() dies
    # of FileExistsError before the status segment is ever created -- which shows up here as
    # the misleading "segment never appeared". Observed once for real, for shared_dict and
    # status; _heartbeat joined the same risk when roadmap item 16 added it to
    # prepare_shared_buffer, since `_reap()`'s Process.terminate() kills a hung child without
    # running `_shutdown()`, so nothing unlinks it either.
    _unlink_quietly(f"{name}_shared_dict")
    _unlink_quietly(f"{name}_status")
    _unlink_quietly(f"{name}_heartbeat")
    minion = _CrashAfterSomeTicks(name)
    minion.run()

    # Attach the way a peer does: by name, once the child has created the segment.
    status = None
    deadline = perf_counter() + JOIN_TIMEOUT
    while status is None and perf_counter() < deadline:
        try:
            status = SharedNdarray(f"{name}_status", lock=SHAREDLOCK, create=False)
        except Exception:
            status = None

    if status is None:
        problems.append("the status segment never appeared; check the probe")
        _reap(minion)
        return problems

    try:
        minion.Process.join(timeout=JOIN_TIMEOUT)
        if minion.Process.is_alive():
            problems.append("the crashing minion hung instead of exiting")
            _reap(minion)
            return problems

        if minion.Process.exitcode != 0:
            problems.append(
                f"child exited {minion.Process.exitcode}, expected 0 -- the exception "
                f"escaped innerLoop instead of being handled"
            )

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            reported = status.read()
        value = None if reported is None else int(np.asarray(reported).ravel()[0])
        if value != -2:
            problems.append(
                f"a peer still reads status {value!r} after the crash, expected -2; "
                f"the minion looks alive to everyone"
            )
    finally:
        try:
            status.close()
        except Exception:
            pass
        _reap(minion)
    return problems


def _reap(minion):
    if minion.Process is not None and minion.Process.is_alive():
        minion.Process.terminate()
        minion.Process.join(timeout=2.0)


def check_status_poll_stays_responsive():
    """A minion must notice a peer's kill signal within a bounded time.

    innerLoop no longer re-reads its status on every iteration -- that read is a
    SharedNdarray.read() and was 89 % of an iteration -- so it is rate-limited by
    `BaseMinion.STATUS_POLL_INTERVAL`. That trades reaction time for the read, and this
    check pins the side of the trade that could regress silently: if the rate limit were
    ever gated on something that stops advancing, or set to a tick-derived value that grows
    with the refresh interval, a minion would stop reacting and only the shutdown timeout
    in AbstractGUIAPP would catch it -- ten seconds later.

    The assertion is loose (300 ms against a 5 ms bound) because it is here to catch "never
    notices", not to measure latency -- a tight bound would be flaky on a loaded machine,
    and PROJECT_OVERVIEW 2.3 has the actual numbers. Loose is still not useless: it caught a
    1030 ms reaction caused by `SharedNdarray.terminate()` retrying for a full second while
    this very check held a handle on the segment.
    """
    problems = []
    name = "FP_BUSY"
    budget = max(0.3, BaseMinion.STATUS_POLL_INTERVAL * 20)
    _unlink_quietly(f"{name}_shared_dict")
    _unlink_quietly(f"{name}_status")
    _unlink_quietly(f"{name}_heartbeat")
    minion = _BusyMinion(name, refresh_interval=20)
    minion.run()

    status = None
    deadline = perf_counter() + JOIN_TIMEOUT
    while status is None and perf_counter() < deadline:
        try:
            status = SharedNdarray(f"{name}_status", lock=SHAREDLOCK, create=False)
        except Exception:
            status = None
    if status is None:
        _reap(minion)
        return ["the status segment never appeared; check the probe"]

    try:
        sleep(0.3)  # let it get past initialize() and into the loop
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            status.write(np.array([-1], dtype=np.int64))  # what kill_minion does
        t0 = perf_counter()
        minion.Process.join(timeout=JOIN_TIMEOUT)
        reaction = perf_counter() - t0

        if minion.Process.is_alive():
            problems.append(f"never reacted to status=-1 within {JOIN_TIMEOUT:.0f} s")
        elif reaction > budget:
            problems.append(
                f"took {reaction*1000:.0f} ms to react to status=-1, expected well under "
                f"{budget*1000:.0f} ms (STATUS_POLL_INTERVAL is "
                f"{BaseMinion.STATUS_POLL_INTERVAL*1000:.0f} ms)"
            )
    finally:
        try:
            status.close()
        except Exception:
            pass
        _reap(minion)
    return problems


def _attach_heartbeat(name, deadline):
    heartbeat = None
    while heartbeat is None and perf_counter() < deadline:
        try:
            heartbeat = shared_memory.SharedMemory(name=f"{name}_heartbeat")
        except FileNotFoundError:
            sleep(0.02)
    return heartbeat


def _read_heartbeat(heartbeat):
    return int.from_bytes(bytes(heartbeat.buf[0:4]), "little")


def check_heartbeat_reflects_liveness():
    """The heartbeat counter must advance while running and freeze on a real hang (item 16).

    `status` alone cannot distinguish "running normally" from "stuck forever inside
    on_time() after setting status to 1" -- both read back as 1, since nothing in that
    path ever writes to the status segment again. The heartbeat is a second, independent
    signal for exactly that gap: it advances in `innerLoop`, at the bottom of the spin
    loop, only on the iterations where control actually gets there. A hang inside `main()`
    never reaches that point, so the counter cannot advance no matter how long the process
    keeps "running" by every other measure.

    Two phases, sequential rather than concurrent to keep the failure attributable: a
    normal ticker must show the counter moving; a minion hung inside its first callback
    must show it frozen -- while `status` is checked in the same phase and confirmed to
    still claim "alive", which is the point being pinned, not an unrelated assumption.
    """
    problems = []
    sample_gap = BaseMinion.HEARTBEAT_INTERVAL * 4  # several bump intervals, not one

    for label, minion_cls, expect_advance in (
        ("FP_HB_NORMAL", _TicksNormally, True),
        ("FP_HB_HANGS", _HangsInsideOnTime, False),
    ):
        for suffix in ("_shared_dict", "_status", "_heartbeat"):
            _unlink_quietly(f"{label}{suffix}")
        minion = minion_cls(label, refresh_interval=5)
        minion.run()
        heartbeat = None
        try:
            heartbeat = _attach_heartbeat(label, perf_counter() + JOIN_TIMEOUT)
            if heartbeat is None:
                problems.append(f"[{label}] heartbeat segment never appeared")
                continue

            sleep(0.3)  # past initialize() and, for the hang case, into the hang
            first = _read_heartbeat(heartbeat)
            sleep(sample_gap)
            second = _read_heartbeat(heartbeat)
            advanced = second != first

            if advanced != expect_advance:
                problems.append(
                    f"[{label}] heartbeat {first} -> {second} over {sample_gap*1000:.0f} ms, "
                    f"expected {'an advance' if expect_advance else 'no change'}"
                )

            if not expect_advance:
                # The point of the check: status must still look fine on its own.
                status = None
                try:
                    status = SharedNdarray(f"{label}_status", lock=SHAREDLOCK, create=False)
                    still_claims_alive = bool(status.read() > 0)  # array([True]) is not True
                except Exception:
                    still_claims_alive = None
                finally:
                    if status is not None:
                        status.close()
                if still_claims_alive is not True:
                    problems.append(
                        f"[{label}] status stopped saying 'alive' too ({still_claims_alive!r}); "
                        f"that would mean the hang isn't isolated to on_time(), so this case "
                        f"doesn't prove heartbeat catches something status misses"
                    )
        finally:
            if heartbeat is not None:
                try:
                    heartbeat.close()
                except Exception:
                    pass
            _reap(minion)
            for suffix in ("_shared_dict", "_status", "_heartbeat"):
                _unlink_quietly(f"{label}{suffix}")
    return problems


def check_disconnect_tolerates_a_missing_peer():
    """disconnect() must not raise for a peer that was never linked (B3).

    `connect()` populates `_queue`; `_registered_buffer_handle` and `_linked_minion` are
    populated only by a *successful* `link_minion`. A peer that was not up within
    `build_init_conn`'s 1 s timeout therefore has a queue and nothing else, and the
    KeyError this used to raise aborted the rest of `_shutdown()` -- so the shared
    segments were never terminated and the child exited 1.
    """
    problems = []
    minion = BaseMinion("FP_DISC")
    # The state connect() leaves behind for a peer that never came up.
    minion._queue = {"NEVER_CAME_UP": _FakeQueue()}

    try:
        minion.disconnect("NEVER_CAME_UP")
    except Exception as exc:
        problems.append(f"disconnect() raised {type(exc).__name__}: {exc}")
        return problems

    if "NEVER_CAME_UP" in minion._queue:
        problems.append("disconnect() left the queue entry behind")
    if not minion._queue["NEVER_CAME_UP"].closed if "NEVER_CAME_UP" in minion._queue else False:
        problems.append("disconnect() did not close the queue")

    # Idempotent: _shutdown() used to run the same loop twice.
    try:
        minion.disconnect("NEVER_CAME_UP")
    except Exception as exc:
        problems.append(f"a second disconnect() raised {type(exc).__name__}: {exc}")
    return problems


class _FakeQueue:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def check_ndarray_write_takes_the_write_lock():
    """SharedNdarray.write() must ask for 'w', and must release it on failure (A4).

    Asking for 'r' meant a write announced itself as a reader, so another writer and any
    reader were admitted while it was in progress and a half-written frame was visible in
    the preview. This does not make the lock sound -- there is still no reader count, and
    that half is still in test_core_multiprocess's KNOWN_DEFECTS -- it only stops write()
    from actively misreporting what it is doing.
    """
    problems = []
    seg = "fp_ndarray"
    zeros = np.zeros((4, 4), dtype=np.uint8)
    _unlink_quietly(seg)
    buf = SharedNdarray(seg, lock=SHAREDLOCK, data=zeros, create=True)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            if not buf.aquire_RWlock("r", timeout=100):
                return ["could not put a reader in; check the probe"]

            # A writer must now be refused while that reader holds the segment.
            buf.write(np.ones((4, 4), dtype=np.uint8))
            byte = buf._read_lockbyte()
            if byte != "r":
                problems.append(f"lock byte is {byte!r} while a reader holds it, expected 'r'")
            buf.release_RWlock()
            if buf.read().any():
                problems.append("the write went through while a reader was inside")

            # A raise inside the critical section must still release the lock.
            try:
                buf.write(np.ones((5, 5), dtype=np.uint8))
            except Exception:
                pass
            else:
                problems.append("a shape-mismatched write did not raise")
            byte = buf._read_lockbyte()
            if byte not in (" ", "\x00"):
                problems.append(f"lock byte left at {byte!r} after a failed write")

            # And the segment must still be usable afterwards.
            buf.write(np.ones((4, 4), dtype=np.uint8))
            if not (buf.read() == 1).all():
                problems.append("the segment is no longer writable after a failed write")
    finally:
        try:
            buf.close()
        except Exception:
            pass
        _unlink_quietly(seg)
    return problems


def check_a_buffer_write_does_not_overtake_deferred_dict_writes():
    """A buffer-backed state must not become visible before the dict states set before it.

    The two storages publish on different schedules: a `SharedNdarray` write lands
    immediately, while `SharedDict` writes are coalesced and published at the tick
    boundary (item 10). Program order between them was therefore not preserved -- a minion
    that writes a directory and *then* raises a start flag published the flag first.

    That is not hypothetical. The application's GUI sets `SaveDir`, `SaveName` and
    `StreamingDevices` (dict states) and then `StreamToDisk` (buffer-backed) in that
    order; on 2026-08-06 SCAN saw `StreamToDisk` go true with `SaveDir` still empty,
    refused to open its files, and that session has no SCAN recording. It appeared the
    day the rig first ran a library with item 10 in it.

    `set_state` now flushes the dict before a buffer write. Verified through a *second*
    handle on the same segment, which is what a peer holds -- the owner's own read would
    be satisfied by the pending overlay and would pass either way.
    """
    problems = []
    dict_seg, buf_seg = "fp_order_dict", "fp_order_buf"
    _unlink_quietly(dict_seg)
    _unlink_quietly(buf_seg)

    owner_dict = SharedDict(dict_seg, lock=SHAREDLOCK, create=True, size=2 ** 14)
    flag_buffer = SharedNdarray(buf_seg, lock=SHAREDLOCK,
                                data=np.zeros(1, dtype=np.uint8), create=True)
    peer_dict = None
    try:
        owner_dict["SaveDir"] = ""
        owner_dict[contract.BUFFER_PREFIX + "StreamToDisk"] = False
        # The dict records the buffer's *name* under the plain key; that redirection is
        # how set_state decides which storage a state lives in.
        owner_dict["StreamToDisk"] = contract.BUFFER_PREFIX + "StreamToDisk"
        owner_dict.flush()

        stub = types.SimpleNamespace(
            _shared_dict=owner_dict,
            _shared_buffer={contract.BUFFER_PREFIX + "StreamToDisk": flag_buffer},
            error=lambda msg: problems.append(f"set_state reported: {msg}"),
        )
        owner_dict.defer_writes(True)

        peer_dict = SharedDict(dict_seg, lock=SHAREDLOCK)

        # The GUI's order: the directory, then the flag, inside one tick.
        BaseMinion.set_state(stub, "SaveDir", "D:/data/20260806_112302")
        if peer_dict["SaveDir"] != "":
            problems.append("the dict write was published early; the deferral is not in "
                            "force and this check cannot see what it is for")
        BaseMinion.set_state(stub, "StreamToDisk", True)

        seen_dir = peer_dict["SaveDir"]
        seen_flag = bool(flag_buffer.read()[0])
        if seen_flag and seen_dir != "D:/data/20260806_112302":
            problems.append(f"a peer sees StreamToDisk={seen_flag} with SaveDir={seen_dir!r}: "
                            "the buffer write overtook the dict writes made before it")
        if owner_dict.has_pending_writes:
            problems.append("dict writes were still pending after a buffer-backed write")
    finally:
        for handle in (peer_dict, owner_dict, flag_buffer):
            try:
                if handle is not None:
                    handle.close()
            except Exception:
                pass
        _unlink_quietly(dict_seg)
        _unlink_quietly(buf_seg)
    return problems


def check_streaming_buffer_updates_the_local_copy():
    """set_streaming_buffer() must refresh the local copy even when shared (A1).

    `_streaming()` writes `_streaming_buffers[name][0]` -- the local copy -- straight to
    disk. For a shared buffer this method used to write only the shared state, so the
    local copy kept the frame it was created with and a whole session recorded that one
    frame over and over. The function that would have refreshed it,
    `get_streaming_buffer()`, is called nowhere in either repository.
    """
    from miniPoly.compiler.prototypes import StreamingCompiler

    problems = []
    written = {}
    stub = types.SimpleNamespace(
        _streaming_buffers={"frame": ["FIRST_FRAME", "movie"]},
        _shared_buffers=["frame"],
        set_state=lambda name, val: written.__setitem__(name, val),
        error=lambda msg: problems.append(f"unexpected error(): {msg}"),
    )

    StreamingCompiler.set_streaming_buffer(stub, "frame", "SECOND_FRAME")

    if stub._streaming_buffers["frame"][0] != "SECOND_FRAME":
        problems.append(
            f"local copy is {stub._streaming_buffers['frame'][0]!r}; _streaming() would "
            f"write that to disk instead of the new frame"
        )
    if written.get("frame") != "SECOND_FRAME":
        problems.append(f"shared state was not written (got {written.get('frame')!r})")

    # The local-only case has to keep working unchanged.
    stub._shared_buffers = []
    written.clear()
    StreamingCompiler.set_streaming_buffer(stub, "frame", "THIRD_FRAME")
    if stub._streaming_buffers["frame"][0] != "THIRD_FRAME":
        problems.append("local-only buffer stopped being updated")
    if written:
        problems.append(f"local-only buffer wrote a shared state: {written!r}")
    return problems


def check_timestamp_accepts_an_empty_timer_minion():
    """An empty timer_minion means "no timer", not a minion named '' (A3).

    Testing only `is not None` sent an empty name into `get_state_from('')`, which cannot
    resolve. `CaImg_App/motor/dynamixel.py` carried a copy of this entire method purely to
    add the second test; that copy has been deleted.
    """
    from miniPoly.compiler.prototypes import StreamingCompiler

    problems = []

    def _fail(*args, **kwargs):
        problems.append("get_state_from() was called for an empty timer minion")
        return None

    stub = types.SimpleNamespace(name="SERVO", _timer_minion="", get_state_from=_fail,
                                get_state=_fail)
    value = StreamingCompiler.get_timestamp(stub)
    if not isinstance(value, float):
        problems.append(f"returned {value!r}, expected a perf_counter() float")

    # A real timer minion must still be consulted.
    seen = []
    stub = types.SimpleNamespace(
        name="SERVO",
        _timer_minion="SCAN",
        get_state_from=lambda minion, state: seen.append((minion, state)) or 2000.0,
        get_state=lambda state: None,
    )
    if StreamingCompiler.get_timestamp(stub) != 2.0:
        problems.append("a real timer minion is no longer divided by 1000")
    if not seen:
        problems.append("a real timer minion was not consulted")
    return problems


def check_buffer_handle_param_round_trips_through_prepare_and_stop():
    """`_prepare_streaming`'s write and `_stop_streaming`'s reset must hit the same
    attribute (B8).

    Before the fix, `_prepare_streaming` set `_bufferHandlerParam` (camelCase) while
    `__init__`/`_stop_streaming` used `_buffer_handle_param` (snake_case), so the reset on
    stop was a no-op and a stale value from a previous session survived into the next one.
    """
    from miniPoly.compiler.prototypes import StreamingCompiler
    import tempfile

    problems = []
    tmp_dir = tempfile.mkdtemp()
    sentinel = "SENTINEL-NOT-YET-WRITTEN"
    stub = types.SimpleNamespace(
        _trigger_minion="GUI",
        name="TEST",
        _streaming_buffers={},
        _buffer_handle_param=sentinel,
        get_state_from=lambda minion, key: tmp_dir if key == "SaveDir" else "session",
        error=lambda msg: problems.append(f"unexpected error(): {msg}"),
    )
    err = StreamingCompiler._prepare_streaming(stub)
    if err:
        problems.append("_prepare_streaming reported an error against a fresh temp dir")
    if stub._buffer_handle_param is sentinel:
        problems.append("_prepare_streaming did not write _buffer_handle_param at all")

    stub.streaming = True
    stub._state_stream_handler = types.SimpleNamespace(close=lambda: None)
    stub._buffer_streaming_handle = {}
    stub._state_stream_fn = None
    stub._state_stream_writer = None
    stub._streaming_start_time = 0
    StreamingCompiler._stop_streaming(stub)
    if stub._buffer_handle_param != {}:
        problems.append(
            f"_stop_streaming left _buffer_handle_param as {stub._buffer_handle_param!r}, "
            f"expected {{}} -- the reset did not take effect"
        )
    return problems


def check_prepare_streaming_reports_missing_name_not_typeerror():
    """A None `SaveName` must produce the "undefined parameter" message, not a TypeError
    (B9).

    `get_state_from(...) + "_" + self.name` used to run before the None check on the very
    next line, so a missing save name crashed `_prepare_streaming` outright instead of
    reporting it through `error()` like every other missing parameter.
    """
    from miniPoly.compiler.prototypes import StreamingCompiler

    problems = []
    error_calls = []
    stub = types.SimpleNamespace(
        _trigger_minion="GUI",
        name="TEST",
        _streaming_buffers={},
        _buffer_handle_param={},
        get_state_from=lambda minion, key: None,
        error=lambda msg: error_calls.append(msg),
    )
    try:
        err = StreamingCompiler._prepare_streaming(stub)
    except TypeError as exc:
        problems.append(f"raised TypeError instead of reporting an error: {exc}")
        return problems
    if not err:
        problems.append("did not report an error for a missing SaveName")
    if not any("undefined parameter" in m.lower() for m in error_calls):
        problems.append(f"error() was not called with the missing-parameter message; got {error_calls!r}")
    return problems


def check_last_row_matches_what_streaming_compares(tmp_path=None):
    """`_start_streaming` must seed `_last_row` with the same slice `_streaming()`
    compares against (B7).

    `_last_row` used to keep the leading timestamp `val_row` has; `_streaming()` compares
    against `val_row[1:]`, which has one fewer element, so the very first post-start
    comparison was between lists of different lengths and could never match.
    """
    from miniPoly.compiler.prototypes import StreamingCompiler
    import tempfile

    problems = []
    tmp_dir = tempfile.mkdtemp()
    csv_path = f"{tmp_dir}/probe.csv"
    stub = types.SimpleNamespace(
        name="TEST",
        _streaming_states={"a": None},
        _streaming_buffers={},
        _buffer_streaming_handle={},
        _state_stream_fn=csv_path,
        get_streaming_state=lambda name: 42,
        get_timestamp=lambda: 0.0,
        watch_state=lambda name, val: None,
    )
    StreamingCompiler._start_streaming(stub)
    try:
        if stub._last_row != [42]:
            problems.append(f"_last_row is {stub._last_row!r} right after _start_streaming, "
                            f"expected [42] (val_row without the leading timestamp)")
    finally:
        stub._state_stream_handler.close()
    return problems


def check_gui_survives_an_empty_window_list():
    """An empty allWindows() must not be read as "every window is hidden" (B4).

    `any([])` is False, so an `on_time` tick that landed before the window's `show()`
    closed the whole application. Seen as "sometimes it exits right after starting".
    """
    from miniPoly.processor.GUI import AbstractGUIAPP

    problems = []
    calls = []

    class _Probe(AbstractGUIAPP):
        def __init__(self, windows):
            # Skip AbstractGUIAPP.__init__: it wants a compiler class and a Qt theme, and
            # neither is involved in the decision under test.
            self._app = types.SimpleNamespace(allWindows=lambda: windows)

        def shutdown(self):
            calls.append(True)

    _Probe([]).poll_GUI_windows()
    if calls:
        problems.append("an empty window list still triggered shutdown()")

    calls.clear()
    _Probe([types.SimpleNamespace(isVisible=lambda: False)]).poll_GUI_windows()
    if not calls:
        problems.append("a genuinely hidden window no longer triggers shutdown()")

    calls.clear()
    _Probe([types.SimpleNamespace(isVisible=lambda: True)]).poll_GUI_windows()
    if calls:
        problems.append("a visible window triggered shutdown()")
    return problems


def check_logger_does_not_block_on_an_empty_queue():
    """LoggerMinion.main() must return on an empty queue, and must not spin (B5).

    `dequeue(True)` blocks, and while blocked it cannot observe the reporters' status, so
    once the other minions went quiet the logger was stuck -- although in VR_init.py it is
    started last and is meant to exit last. Making it non-blocking removes the pacing that
    blocking provided, so the empty branch has to sleep or it burns a core.
    """
    from queue import Empty

    from miniPoly.processor.Logging import LoggerMinion

    problems = []
    handled = []
    stub = types.SimpleNamespace(
        hasConfig=True,
        logger=object(),
        IDLE_POLL_INTERVAL=LoggerMinion.IDLE_POLL_INTERVAL,
        dequeue=lambda block: (_ for _ in ()).throw(Empty()),
        handle=lambda record: handled.append(record),
        poll_reporter=lambda: False,
        shutdown=lambda: problems.append("shutdown() called while reporters were alive"),
    )

    t0 = perf_counter()
    LoggerMinion.main(stub)
    elapsed = perf_counter() - t0

    if elapsed > 1.0:
        problems.append(f"main() took {elapsed:.2f} s on an empty queue -- it is still blocking")
    if stub.IDLE_POLL_INTERVAL <= 0:
        problems.append("IDLE_POLL_INTERVAL must be positive or an idle logger spins")
    if handled:
        problems.append(f"handle() was called with {handled!r} for an empty queue")

    # A record that is there must still be handled.
    record = object()
    stub.dequeue = lambda block: record
    LoggerMinion.main(stub)
    if handled != [record]:
        problems.append(f"a queued record was not handled (handled={handled!r})")
    return problems


def check_logger_drains_records_still_in_flight_at_shutdown():
    """`shutdown()` must wait for silence, not for `queue.empty()`.

    `multiprocessing.Queue.empty()` cannot answer the question the drain is asking.
    `put()` does not write to the pipe; it appends to a buffer that a per-process feeder
    thread drains asynchronously, so a record can be logged, `put`, and still be invisible
    to the reader afterwards. `empty()` reports what has arrived, never what is coming.

    The records in flight at shutdown are precisely a minion's *last* ones -- why it
    stopped, and whether it stopped cleanly. `examples/two_minions.py` lost both of its
    final lines to this, which is how it was found: the documented output of the tutorial
    could not be reproduced.

    A queue that reports empty and then yields two more records is exactly that race,
    made deterministic.
    """
    from queue import Empty

    from miniPoly.processor.Logging import LoggerMinion

    problems = []
    handled = []
    late = ["reading reached 50.0", "FOLLOWER is off"]

    class InFlightQueue:
        """Empty on the first look, then two records arrive -- as a feeder thread does."""

        def empty(self):
            return True

        def get(self, timeout=None):
            if late:
                return late.pop(0)
            raise Empty()

    stub = types.SimpleNamespace(
        _stopping=False,
        queue=InFlightQueue(),
        # Shorter than the real values: this test asserts the loop's shape, and paying
        # the production grace period for it would add a quarter-second for nothing.
        DRAIN_GRACE=0.05,
        IDLE_POLL_INTERVAL=0.001,
        name="LOGGER",
        handle=handled.append,
        info=handled.append,
        set_state_to=lambda *a: None,
    )

    t0 = perf_counter()
    LoggerMinion.shutdown(stub)
    elapsed = perf_counter() - t0

    for record in ("reading reached 50.0", "FOLLOWER is off"):
        if record not in handled:
            problems.append(
                f"a record still in flight was dropped: {record!r} never reached handle()"
            )
    if handled and handled[-1] != '----------------- STOP LOGGING -----------------':
        problems.append(f"the stop banner is not last: {handled[-1]!r}")
    # The grace is a bound, not a floor to grow without limit: each record resets it, so
    # two records cost about two graces, not one per queued item forever.
    if elapsed > 1.0:
        problems.append(f"shutdown() took {elapsed:.2f} s -- the drain does not terminate")

    # Idempotent: main() can call shutdown() again before innerLoop notices the status
    # went negative, and that window used to log the banner twice.
    before = len(handled)
    LoggerMinion.shutdown(stub)
    if len(handled) != before:
        problems.append("a second shutdown() call was not a no-op")
    return problems


def check_clean_exit_prints_no_ignored_exception():
    """A process that creates a segment and never closes it must still exit silently.

    Every entry point's **parent** process constructs the minions, so `__init__`'s first
    write opens a held-open `atomicview` per segment there -- and `close()` only ever runs
    in the child, from `_shutdown()`. `atomics.AtomicViewContext.__del__` raises ValueError
    when the context is still open, so before `SharedBuffer.__del__` / `SharedNdarray.__del__`
    released it, **every clean exit printed one ignored traceback per segment**: three for
    the two-minion example in the README. Harmless, and the first thing a new user sees.

    Run in a subprocess on purpose: the interpreter prints these during finalisation, after
    any in-process hook could observe them.
    """
    import subprocess

    name = "check_clean_exit_segment"
    _unlink_quietly(name)
    _unlink_quietly(name + "_generation")

    program = (
        "import numpy as np\n"
        "from multiprocessing import Lock\n"
        "from miniPoly.core.buffer import SharedNdarray\n"
        f"buf = SharedNdarray({name!r}, Lock(), np.zeros(4))\n"
        # No close(), no terminate() -- exactly what the parent process does.
    )
    proc = subprocess.run(
        [sys.executable, "-c", program],
        capture_output=True,
        text=True,
        timeout=60,
    )
    _unlink_quietly(name)
    _unlink_quietly(name + "_generation")

    problems = []
    if proc.returncode != 0:
        problems.append(f"the subprocess exited {proc.returncode}; stderr:\n{proc.stderr}")
    if "Exception ignored" in proc.stderr:
        problems.append(
            "a clean exit still prints an ignored exception -- a held-open atomicview was "
            f"left to the garbage collector; stderr:\n{proc.stderr}"
        )
    return problems


def _unlink_quietly(name):
    from multiprocessing import shared_memory
    try:
        shared_memory.SharedMemory(name=name).unlink()
    except (FileNotFoundError, OSError):
        pass


def _clear_segments(name):
    for suffix in ("_shared_dict", "_shared_dict_generation", "_status", "_heartbeat"):
        _unlink_quietly(f"{name}{suffix}")


def _link_as_peer(observer, name, deadline):
    """Link `observer` to a running minion the way build_init_conn does, and wait for it."""
    while perf_counter() < deadline:
        if observer.link_minion(name) == 0:
            return True
        sleep(0.02)
    return False


def check_declaration_seal_bounds_the_wait():
    """A peer that has finished declaring must not be waited on (B11, roadmap item 19).

    `link_minion` succeeding proves the peer's segment exists, not that the states in it
    do: the states are created by the compiler's `__init__`, which is application code and
    took 3.2 s in the 2025-11-28 rig session log. The only defence was a fixed
    300-iteration retry in `get_foreign_state`, and it runs inside the caller's own tick --
    for the GUI that is a frozen Qt event loop, observed three times in one session for
    camera buffers whose names come from a runtime video format.

    `FRAMEWORK_SEALED` splits the two cases the fixed retry could not tell apart, and this
    check pins both directions, because getting either one wrong is silent:

    1. **sealed and absent** -- the state is never coming, so the answer must be immediate.
       Waiting here is the pure-loss case.
    2. **not sealed yet, arrives late** -- the peer is still constructing, so the wait is
       exactly right and must still return the real value.

    Case 2 also pins the per-attempt `err_code` reset. `err_code` used to latch at 1 on the
    first miss, so `if err_code == 0: break` could never fire again: the loop ran all 300
    iterations even when the value showed up on attempt two, and then reported the state as
    unknown while returning it. That made every late state cost the full timeout, which is
    most of what B11's log lines were measuring.

    Note what is *not* used here: item 16's heartbeat cannot bound this wait, although B11's
    entry says it can. `initialize()` runs inside `innerLoop`, so a peer still building its
    compiler has never reached the heartbeat line -- its counter sits at 0, indistinguishable
    from a hung peer. The seal is the only signal that separates them.
    """
    problems = []
    timeout_s = 3.0  # get_foreign_state's default `timeout` of 3000 ms
    immediate_budget = 0.5
    late_budget = 1.0  # above DECLARE_DELAY, below DECLARE_DELAY + SEAL_DELAY

    # --- case 1: sealed peer, state that does not exist -----------------------
    name = "FP_SEALED"
    _clear_segments(name)
    peer = _SealsImmediately(name, refresh_interval=5)
    peer.run()
    observer = BaseMinion("FP_OBSERVER_A")
    try:
        deadline = perf_counter() + JOIN_TIMEOUT
        if not _link_as_peer(observer, name, deadline):
            problems.append(f"[{name}] could not link to the peer; check the probe")
        else:
            while (observer.declarations_sealed_by(name) is not True
                   and perf_counter() < deadline):
                sleep(0.02)
            if observer.declarations_sealed_by(name) is not True:
                problems.append(
                    f"[{name}] the peer never published {contract.FRAMEWORK_SEALED!r}; "
                    f"initialize() returned, so seal_declarations() should have run"
                )
            else:
                t0 = perf_counter()
                value = observer.get_foreign_state(name, "no_such_state")
                elapsed = perf_counter() - t0
                if value is not None:
                    problems.append(f"[{name}] a missing state returned {value!r}, expected None")
                if elapsed > immediate_budget:
                    problems.append(
                        f"[{name}] a sealed peer's missing state took {elapsed:.2f} s "
                        f"(budget {immediate_budget:.1f} s, old fixed retry {timeout_s:.0f} s) "
                        f"-- the wait is not bounded by the seal"
                    )
    finally:
        # _reap rather than peer.shutdown(): `shutdown()` writes through
        # `self._shared_buffer`, which only the child process ever populates.
        _reap(peer)
        observer.disconnect(name)
        _clear_segments(name)

    # --- case 2: unsealed peer, state that arrives late -----------------------
    name = "FP_LATE"
    _clear_segments(name)
    peer = _DeclaresLate(name, refresh_interval=5)
    peer.run()
    observer = BaseMinion("FP_OBSERVER_B")
    try:
        if not _link_as_peer(observer, name, perf_counter() + JOIN_TIMEOUT):
            problems.append(f"[{name}] could not link to the peer; check the probe")
        else:
            t0 = perf_counter()
            value = observer.get_foreign_state(name, LATE_STATE)
            elapsed = perf_counter() - t0
            if value != LATE_VALUE:
                problems.append(
                    f"[{name}] got {value!r} for a state declared {DECLARE_DELAY:.1f} s in, "
                    f"expected {LATE_VALUE!r} -- failing fast broke the legitimate wait"
                )
            if elapsed > late_budget:
                problems.append(
                    f"[{name}] waited {elapsed:.2f} s for a state that appeared after "
                    f"{DECLARE_DELAY:.1f} s (budget {late_budget:.1f} s) -- the loop no longer "
                    f"breaks when the value arrives, only when the peer seals "
                    f"{SEAL_DELAY:.1f} s later"
                )
    finally:
        # _reap rather than peer.shutdown(): `shutdown()` writes through
        # `self._shared_buffer`, which only the child process ever populates.
        _reap(peer)
        observer.disconnect(name)
        _clear_segments(name)

    return problems


CHECKS = (
    ("crashed minion reports its death (B2)", check_crashed_minion_reports_its_death),
    ("status poll stays responsive", check_status_poll_stays_responsive),
    ("heartbeat reflects liveness (item 16)", check_heartbeat_reflects_liveness),
    ("declaration seal bounds the wait (B11)", check_declaration_seal_bounds_the_wait),
    ("a buffer write does not overtake deferred dict writes", check_a_buffer_write_does_not_overtake_deferred_dict_writes),
    ("disconnect tolerates a missing peer (B3)", check_disconnect_tolerates_a_missing_peer),
    ("ndarray write takes the write lock (A4)", check_ndarray_write_takes_the_write_lock),
    ("streaming buffer updates the local copy (A1)", check_streaming_buffer_updates_the_local_copy),
    ("timestamp accepts an empty timer minion (A3)", check_timestamp_accepts_an_empty_timer_minion),
    ("buffer_handle_param round-trips through prepare/stop (B8)",
     check_buffer_handle_param_round_trips_through_prepare_and_stop),
    ("prepare_streaming reports a missing name, not TypeError (B9)",
     check_prepare_streaming_reports_missing_name_not_typeerror),
    ("last_row matches what streaming compares (B7)", check_last_row_matches_what_streaming_compares),
    ("GUI survives an empty window list (B4)", check_gui_survives_an_empty_window_list),
    ("logger does not block on an empty queue (B5)", check_logger_does_not_block_on_an_empty_queue),
    ("logger drains records still in flight at shutdown",
     check_logger_drains_records_still_in_flight_at_shutdown),
    ("a clean exit prints no ignored exception", check_clean_exit_prints_no_ignored_exception),
)


# --------------------------------------------------------------------------
# pytest entry points
# --------------------------------------------------------------------------

def test_crashed_minion_reports_its_death():
    assert not check_crashed_minion_reports_its_death()


def test_status_poll_stays_responsive():
    assert not check_status_poll_stays_responsive()


def test_heartbeat_reflects_liveness():
    problems = check_heartbeat_reflects_liveness()
    assert not problems, "; ".join(problems)


def test_declaration_seal_bounds_the_wait():
    problems = check_declaration_seal_bounds_the_wait()
    assert not problems, "; ".join(problems)


def test_disconnect_tolerates_a_missing_peer():
    assert not check_disconnect_tolerates_a_missing_peer()


def test_ndarray_write_takes_the_write_lock():
    assert not check_ndarray_write_takes_the_write_lock()


def test_streaming_buffer_updates_the_local_copy():
    assert not check_streaming_buffer_updates_the_local_copy()


def test_timestamp_accepts_an_empty_timer_minion():
    assert not check_timestamp_accepts_an_empty_timer_minion()


def test_buffer_handle_param_round_trips_through_prepare_and_stop():
    problems = check_buffer_handle_param_round_trips_through_prepare_and_stop()
    assert not problems, "; ".join(problems)


def test_prepare_streaming_reports_missing_name_not_typeerror():
    problems = check_prepare_streaming_reports_missing_name_not_typeerror()
    assert not problems, "; ".join(problems)


def test_last_row_matches_what_streaming_compares():
    problems = check_last_row_matches_what_streaming_compares()
    assert not problems, "; ".join(problems)


def test_gui_survives_an_empty_window_list():
    assert not check_gui_survives_an_empty_window_list()


def test_clean_exit_prints_no_ignored_exception():
    assert not check_clean_exit_prints_no_ignored_exception()


def test_logger_does_not_block_on_an_empty_queue():
    assert not check_logger_does_not_block_on_an_empty_queue()


def test_logger_drains_records_still_in_flight_at_shutdown():
    assert not check_logger_drains_records_still_in_flight_at_shutdown()


if __name__ == "__main__":
    mp.freeze_support()
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    print("Note: one deliberate traceback is printed below by the B2 check -- a minion is "
          "crashed on purpose,\n      and reporting it on stderr is part of what that check "
          "verifies.\n")

    failed = False
    for label, fn in CHECKS:
        # A check that raises is a failure, not a reason to abandon the run: against
        # pre-fix code several of these defects surface as an exception rather than as a
        # wrong value, and the remaining checks still need to report.
        try:
            problems = fn()
        except Exception:
            problems = [f"the check itself raised:\n       " + traceback.format_exc().replace("\n", "\n       ")]
        if problems:
            failed = True
            print(f"FAIL {label}")
            for p in problems:
                print(f"       {p}")
        else:
            print(f"OK   {label}")

    raise SystemExit(1 if failed else 0)
