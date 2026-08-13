"""Cross-process behaviour of `miniPoly.core`, including the defects 9b must fix.

Why this test has to exist before the lock repair, not after: the reader-count
defect and the non-atomic test-and-set only manifest when more than one process
touches a segment at the same time. Running the application demonstrates neither
the defect nor its repair, so there is nothing to check a fix against.

The file has two halves.

**Contract checks** are invariants the framework promises and must keep. A failure
here is a regression.

**Known-defect checks** reproduce a defect on purpose and assert that it *still*
reproduces. That sounds backwards, but it is the same baseline pattern
`miniPolyApp/tests/test_app_imports.py` already uses: when 9b lands, these checks
start failing, which is the signal to move the item out of the baseline. A silent
pass would let a half-fix through.

Deliberately low-stress -- 3 processes, small iteration counts, every join
bounded -- so it is safe to run on a modest development machine. Whole file
completes in a few seconds.

Standalone:  python tests/test_core_multiprocess.py
             python tests/test_core_multiprocess.py --perf     (adds timings)
pytest:      pytest tests/test_core_multiprocess.py
"""

import io
import json
import multiprocessing as mp
import os
import sys
import warnings
from contextlib import redirect_stdout
from multiprocessing import shared_memory
from time import perf_counter, sleep

import numpy as np

from miniPoly.core.buffer import SharedBuffer, SharedDict
from miniPoly.core.minion import SHAREDLOCK

N_PROC = 3
N_ITER = 300
JOIN_TIMEOUT = 20.0
SEGMENT_SIZE = 2 ** 13

# Defects reproduced on purpose. Remove an entry here only together with its fix.
# Graduated: "B1-failed-encode-wipes-and-locks-the-segment" was fixed by roadmap
# Stage 1 item 1 and is now the contract check `check_failed_write_is_non_destructive`.
# "lock-byte-test-and-set-is-not-atomic" was fixed by roadmap item 15 (atomic write-lock
# CAS) and is now `check_write_lock_excludes_concurrent_writers`. A4 remains: item 15 was
# scoped to writer-vs-writer only.
KNOWN_DEFECTS = {
    "A4-one-reader-release-admits-a-writer",
    "B2-segment-outlives-its-owner",
    "terminate-after-close-raises",
}


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _unlink_quietly(name):
    try:
        shared_memory.SharedMemory(name=name).unlink()
    except (FileNotFoundError, OSError):
        pass


def _spawn(target, args, n=1):
    """Start n processes, join them with a bound, kill anything still running."""
    procs = [mp.Process(target=target, args=args) for _ in range(n)]
    for p in procs:
        p.start()
    deadline = perf_counter() + JOIN_TIMEOUT
    for p in procs:
        p.join(timeout=max(0.1, deadline - perf_counter()))
    stragglers = [p for p in procs if p.is_alive()]
    for p in stragglers:
        p.terminate()
        p.join(timeout=2.0)
    return [p.exitcode for p in procs], len(stragglers)


# --------------------------------------------------------------------------
# workers (module level so Windows spawn can import them)
# --------------------------------------------------------------------------

def _w_read_key(name, key, out_name):
    """Attach to a foreign SharedDict by name and report whether `key` is there."""
    result = shared_memory.SharedMemory(name=out_name)
    try:
        with SharedDict(name, lock=SHAREDLOCK) as d:
            result.buf[0] = 1 if d.get(key) is not None else 0
    except Exception:
        result.buf[0] = 2
    finally:
        result.close()


def _w_poll_for_key(name, key, out_name, tries=200):
    """Poll a foreign SharedDict until `key` appears. Tests dynamic declaration."""
    result = shared_memory.SharedMemory(name=out_name)
    try:
        for _ in range(tries):
            with SharedDict(name, lock=SHAREDLOCK) as d:
                if key in d.keys():
                    result.buf[1] = 1
                    return
            sleep(0.01)
        result.buf[1] = 0
    except Exception:
        result.buf[1] = 2
    finally:
        result.close()


def _w_guarded_marker(lock_seg, marker_seg, worker_id, iters, hold_s):
    """Occupy the critical section under aquire_RWlock('w') and check exclusivity.

    Lost-update counting is a poor detector here: `aquire_RWlock` costs far more
    than a 4-byte increment, so the collision window is tiny and few iterations
    never hit it. Instead each worker stamps its own id on entry, holds briefly,
    and reads the stamp back on exit. A changed stamp means another writer was
    admitted while this one held the lock -- direct evidence, no statistics.

    Byte 0 holds the current stamp; byte 1 is set to 1 if any violation is seen.
    """
    lock = SharedBuffer(lock_seg, lock=SHAREDLOCK, create=False)
    lock._use_RWLock = True
    marker = shared_memory.SharedMemory(name=marker_seg)
    try:
        for _ in range(iters):
            if not lock.aquire_RWlock("w", timeout=100000):
                continue
            marker.buf[0] = worker_id
            if hold_s:
                sleep(hold_s)
            if marker.buf[0] != worker_id:
                marker.buf[1] = 1
            lock.release_RWlock()
    finally:
        marker.close()
        lock.close()


def _w_create_attach_then_die(name, ready_seg):
    """Create a segment, signal the parent to attach, then die uncleanly.

    B2 is about a peer that has *already mapped* the segment continuing to see a
    stale value. On Windows a segment with no remaining handle is released
    immediately, so the parent has to attach before this process exits -- which is
    exactly the situation a linked minion is in.
    """
    shm = shared_memory.SharedMemory(create=True, name=name, size=64)
    shm.buf[0:4] = (12345).to_bytes(4, "little")
    ready = shared_memory.SharedMemory(name=ready_seg)
    ready.buf[0] = 1               # tell the parent the segment exists
    for _ in range(500):           # wait for the parent to confirm it attached
        if ready.buf[1] == 1:
            break
        sleep(0.01)
    ready.close()
    os._exit(0)


# --------------------------------------------------------------------------
# contract checks
# --------------------------------------------------------------------------

def check_cross_process_visibility():
    """A state written by the owner is readable by a peer that attaches by name."""
    problems = []
    seg, out = "mp_vis_dict", "mp_vis_out"
    _unlink_quietly(seg)
    _unlink_quietly(out)
    result = shared_memory.SharedMemory(create=True, name=out, size=8)
    result.buf[0:8] = b"\x00" * 8
    owner = SharedDict(seg, lock=SHAREDLOCK, create=True, size=SEGMENT_SIZE)
    try:
        owner["timestamp"] = 1764328094123.456
        codes, stuck = _spawn(_w_read_key, (seg, "timestamp", out))
        if stuck:
            problems.append("peer did not finish within the join timeout")
        elif result.buf[0] != 1:
            problems.append(f"peer could not read the state (marker={result.buf[0]})")
        if codes and codes[0] not in (0, None):
            problems.append(f"peer exited with code {codes[0]}")
    finally:
        owner.close()
        _unlink_quietly(seg)
        result.close()
        result.unlink()
    return problems


def check_dynamic_declaration():
    """A state created *after* a peer has attached must still become visible.

    This is the schema-free namespace's core promise: declaration happens at
    runtime, from inside the owning process, and peers discover it by name with no
    schema and no broker.
    """
    problems = []
    seg, out = "mp_dyn_dict", "mp_dyn_out"
    _unlink_quietly(seg)
    _unlink_quietly(out)
    result = shared_memory.SharedMemory(create=True, name=out, size=8)
    result.buf[0:8] = b"\x00" * 8
    owner = SharedDict(seg, lock=SHAREDLOCK, create=True, size=SEGMENT_SIZE)
    try:
        owner["name"] = "OWNER"
        peer = mp.Process(target=_w_poll_for_key, args=(seg, "declared_late", out))
        peer.start()
        sleep(0.2)  # let the peer attach and start polling first
        owner["declared_late"] = [1, 2, 3]
        peer.join(timeout=JOIN_TIMEOUT)
        if peer.is_alive():
            peer.terminate()
            peer.join(timeout=2.0)
            problems.append("peer never observed the late declaration")
        elif result.buf[1] != 1:
            problems.append(
                f"late declaration was not discovered (marker={result.buf[1]})"
            )
    finally:
        owner.close()
        _unlink_quietly(seg)
        result.close()
        result.unlink()
    return problems


def _segment_survived(buf, expected, when):
    """The three properties a failed write must preserve: lock, value, usability.

    Usability is the one that matters: a stuck lock byte is only visible as every
    later read and write on that segment timing out, which at every call site is
    indistinguishable from a legitimately absent state.
    """
    problems = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        byte = buf._read_lockbyte()
        if byte not in (" ", "\x00"):
            problems.append(f"lock byte left at {byte!r} {when}")
        current = buf.read()
        if current != expected:
            problems.append(f"payload is {current!r}, expected {expected!r} {when}")
            return problems
        probe = dict(expected, probe=when)
        try:
            buf.write(probe)
            if buf.read() != probe:
                problems.append(f"segment is no longer writable {when}")
        except Exception as exc:
            problems.append(f"segment is no longer writable {when}: {type(exc).__name__}: {exc}")
        finally:
            try:
                buf.write(expected)
            except Exception:
                pass
    return problems


def check_failed_write_is_non_destructive():
    """A write that cannot complete must leave the segment usable (B1, fixed).

    `SharedBuffer.write` encodes and size-checks before it takes the lock or touches
    the data region, and releases the lock in a `finally`. Two failure modes are
    exercised -- a value stdlib json cannot represent, and a payload larger than the
    region -- and after each one the previous value must still be readable, the lock
    byte must be free, and the next write must land.

    Before the fix either failure zeroed the region and left the lock byte at 'w'
    permanently: the owning minion could no longer read or write its own states, and
    every peer polling it spun, warned, and received None.

    Deliberately not covered, both outside roadmap item 1: `SharedDict.__setitem__`
    keeps the rejected key in its local dict until the next `_refresh()` rebuilds that
    dict from shared memory, and still swallows the traceback into a bare `print`
    instead of logging it. Roadmap item 11 (orjson) removes the trigger itself.
    """
    problems = []
    seg = "mp_b1_dict"
    _unlink_quietly(seg)
    d = SharedDict(seg, lock=SHAREDLOCK, create=True, size=SEGMENT_SIZE)
    buf = d._linked_SharedBuffer
    try:
        d["ok"] = 1.5
        if buf.read() != {"ok": 1.5}:
            return ["baseline write did not land; check the probe"]

        # An ndarray is the realistic trigger now that roadmap item 11 taught the encoder
        # every numpy *scalar* dtype: an array does not belong in the state dict at all --
        # that is what a `b*` SharedNdarray is for -- so encoding it must still raise
        # rather than quietly serialise a frame into an 8 KB segment. Until item 11 this
        # check used np.float32, which was the trigger then and now round-trips.
        try:
            buf.write({"bad": np.arange(3)})
        except TypeError:
            pass
        except Exception as exc:
            problems.append(f"unencodable value raised {type(exc).__name__}, expected TypeError")
        else:
            problems.append("unencodable value did not raise")
        problems += _segment_survived(buf, {"ok": 1.5}, "after an unencodable value")

        try:
            buf.write({"big": "x" * (SEGMENT_SIZE + 1)})
        except ValueError:
            pass
        except Exception as exc:
            problems.append(f"oversized payload raised {type(exc).__name__}, expected ValueError")
        else:
            problems.append("oversized payload did not raise")
        problems += _segment_survived(buf, {"ok": 1.5}, "after an oversized payload")

        # The framework's own path. __setitem__ swallows the failure into stdout, so
        # redirecting it is both noise control and a record of where the error goes.
        swallowed = io.StringIO()
        with warnings.catch_warnings(), redirect_stdout(swallowed):
            warnings.simplefilter("ignore")
            d["bad"] = np.arange(3)
        if "Traceback" not in swallowed.getvalue():
            problems.append("SharedDict.__setitem__ no longer reports the failure at all")
        problems += _segment_survived(buf, {"ok": 1.5}, "after __setitem__ swallowed the failure")
    finally:
        try:
            d.close()
        except Exception:
            pass
        _unlink_quietly(seg)
    return problems


def check_header_release_requires_acquire():
    """`_write_header`/`_read_header` must not release a lock they never acquired (C10).

    A timed-out `acquire()` used to fall through to `release()` unconditionally --
    releasing a lock this process does not hold, which for a real OS mutex can unlock it
    out from under whoever does. Simulated with a stub lock rather than real contention,
    since 0.1 s contention on this specific lock is otherwise rare to trigger.
    """
    problems = []
    seg = "mp_c10_buf"
    _unlink_quietly(seg)

    class _NeverAcquires:
        def acquire(self, timeout=None):
            return False

        def release(self):
            problems.append("release() was called after a failed acquire()")

    buf = SharedBuffer(seg, lock=SHAREDLOCK, data={"v": 1}, size=SEGMENT_SIZE, create=True)
    try:
        buf._lock = _NeverAcquires()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            buf._write_header()
            buf._read_header()
    finally:
        buf._lock = SHAREDLOCK
        buf.close()
        _unlink_quietly(seg)
    return problems


def check_payload_framing_is_length_prefixed():
    """`read` must be bounded by the declared length, not by a NUL terminator (item 9).

    Two properties:

    1. **The tail of the segment is not read at all.** Filling it with bytes that are
       not valid UTF-8 must change nothing. Before the fix `read` decoded the whole
       region, so a single 0xFF byte anywhere past the payload raised
       UnicodeDecodeError, was swallowed into a warning, and the state came back None
       -- verified directly against the old read logic. This is the structural form of
       the performance claim: what makes the read cheap is that the unused region is
       never touched, and this check fails if some later change starts touching it.
    2. **A shorter write does not leave the previous payload's tail readable.** The
       unconditional zero-fill used to guarantee this, and removing it moves the
       guarantee onto the length field. Verified by sabotage rather than against the
       pre-fix code, which had the zero-fill: with `_write_length` stubbed out so the
       old length stands, the read spans the new payload plus the tail of the old one,
       fails to decode, and returns None.

    Not checked here: whether a NUL byte in the *payload* survives. It always did --
    `json.dumps` escapes it to `\\u0000`, so the encoded bytes never contain a literal
    NUL. The terminator only ever constrained which codecs were admissible, which is
    `check_nul_safety` in tests/test_serialization.py, not a property of any value the
    framework actually stores.
    """
    problems = []
    seg = "mp_framing_buf"
    _unlink_quietly(seg)
    buf = SharedBuffer(seg, lock=SHAREDLOCK, data={"v": 1}, size=SEGMENT_SIZE, create=True)
    try:
        payload = {"minion": "SCAN", "timestamp": 1764328094123.456}
        buf.write(payload)

        # 1. Poke invalid UTF-8 into the unused tail. 0xFF is never a valid UTF-8 byte
        # in any position, so a decode of the whole region cannot survive it.
        tail = buf._DATA_OFFSET + len(json.dumps(payload).encode("utf-8"))
        buf._shared_memory.buf[tail:tail + 16] = b"\xff" * 16
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            got = buf.read()
        if got != payload:
            problems.append(f"unreadable bytes past the payload changed the read: got {got!r}")

        # 2. Long then short, with no stale tail.
        buf.write({"pad": "y" * 512})
        buf.write({"pad": "y"})
        got = buf.read()
        if got != {"pad": "y"}:
            problems.append(f"a shorter write left a stale tail readable: got {got!r}")

        # An oversized length must be reported, not raise on the slice.
        buf._write_length(buf.size + 1)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            got = buf.read()
        if got is not None:
            problems.append(f"a length past the region returned {got!r} instead of None")
        if not any("Failed to read" in str(w.message) for w in caught):
            problems.append("a length past the region was not reported as a read failure")
    finally:
        buf.close()
        _unlink_quietly(seg)
    return problems


def _w_bump_generation(seg, iters, out_seg):
    """Attach and write `iters` times, as a foreign writer would (roadmap item 14)."""
    result = shared_memory.SharedMemory(name=out_seg)
    try:
        d = SharedDict(seg, lock=SHAREDLOCK)
        try:
            for i in range(iters):
                d["k"] = i
        finally:
            d.close()
        result.buf[0] = 1
    except Exception:
        result.buf[0] = 2
    finally:
        result.close()


def check_generation_counter_tracks_every_write():
    """The per-segment change counter advances on every write, owner or foreign (item 14).

    Two properties: a single process's own writes (`__setitem__`, `flush`) each advance
    it by exactly one, and concurrent writers across processes land an exact total --
    `fetch_inc` is the same primitive the heartbeat and write-lock CAS already rely on to
    be safe under real contention, applied here to a counter multiple *different*
    processes increment, not just one.
    """
    problems = []
    seg, out = "mp_gen_dict", "mp_gen_out"
    _unlink_quietly(seg)
    _unlink_quietly(out)
    result = shared_memory.SharedMemory(create=True, name=out, size=8)
    result.buf[0:8] = b"\x00" * 8
    owner = SharedDict(seg, lock=SHAREDLOCK, create=True, size=SEGMENT_SIZE)
    try:
        base = owner.generation
        owner["a"] = 1
        if owner.generation != base + 1:
            problems.append(f"__setitem__ advanced generation to {owner.generation}, "
                            f"expected {base + 1}")

        owner.defer_writes(True)
        owner["b"] = 2
        owner["c"] = 3
        if owner.generation != base + 1:
            problems.append("a deferred write advanced generation before flush")
        owner.flush()
        if owner.generation != base + 2:
            problems.append(f"flush() advanced generation to {owner.generation}, "
                            f"expected {base + 2}")
        owner.defer_writes(False)

        before_concurrent = owner.generation
        n_per_proc, n_procs = 200, 3
        codes, stuck = _spawn(_w_bump_generation, (seg, n_per_proc, out), n=n_procs)
        if stuck:
            problems.append("a foreign writer did not finish within the join timeout")
        after = owner.generation
        expected = before_concurrent + n_per_proc * n_procs
        if after != expected:
            problems.append(f"generation is {after} after {n_procs} concurrent foreign "
                            f"writers x {n_per_proc} writes each, expected {expected} "
                            f"(lost {expected - after} increments)")
    finally:
        owner.close()
        _unlink_quietly(seg)
        result.close()
        result.unlink()
    return problems


def check_numpy_scalars_survive_a_real_write():
    """Every numpy scalar dtype must round-trip as its Python type (item 11, B1).

    This is B1's realistic trigger, closed at the encoder rather than by swapping the
    codec. Two halves, and the second is the reason `orjson` was rejected for the job:

    1. All eight dtypes encode, and come back as `int`/`float`/`bool`. The type matters
       as much as the value -- `dockableGUI._update_surveillance_state_list` dispatches
       on `val_type in [int, float, bool]`, so a numpy type surviving the round trip
       would drop the state from the live plots instead of raising.
    2. NaN and +-Infinity survive as themselves. `orjson` maps them to `null`, i.e. to
       `None`, which is reachable here: OMS builds its rotation states through
       `np.nanmean`, which returns NaN for an all-NaN window, and
       `dockableGUI.rotate_sphere` then calls `np.isnan(r)` on one of them -- TypeError
       for None. Pinning this keeps a future codec swap from reintroducing it silently.
    """
    problems = []
    seg = "mp_numpy_dict"
    _unlink_quietly(seg)
    buf = SharedBuffer(seg, lock=SHAREDLOCK, data={"v": 0}, size=SEGMENT_SIZE, create=True)
    try:
        dtypes = {
            "float64": (np.float64(2.5), 2.5, float),
            "float32": (np.float32(2.5), 2.5, float),
            "float16": (np.float16(2.5), 2.5, float),
            "int64": (np.int64(-7), -7, int),
            "int32": (np.int32(-7), -7, int),
            "int8": (np.int8(-7), -7, int),
            "uint64": (np.uint64(7), 7, int),
            "bool_": (np.bool_(True), True, bool),
        }
        for name, (value, expected, expected_type) in dtypes.items():
            try:
                buf.write({"v": value})
            except Exception as exc:
                problems.append(f"np.{name} raised on write: {type(exc).__name__}: {exc}")
                continue
            got = buf.read()["v"]
            if got != expected:
                problems.append(f"np.{name} read back as {got!r}, expected {expected!r}")
            elif type(got) is not expected_type:
                problems.append(f"np.{name} read back as {type(got).__name__}, "
                                f"expected {expected_type.__name__}")

        for name, value in (("nan", float("nan")), ("np.float64 nan", np.float64("nan")),
                            ("np.float32 nan", np.float32("nan"))):
            try:
                buf.write({"v": value})
            except Exception as exc:
                problems.append(f"{name} raised on write: {type(exc).__name__}: {exc}")
                continue
            got = buf.read()["v"]
            if not (isinstance(got, float) and np.isnan(got)):
                problems.append(f"{name} did not survive: read back {got!r} "
                                f"({type(got).__name__}); np.isnan on it would raise")
        for name, value, expected in (("+inf", float("inf"), np.inf),
                                      ("-inf", float("-inf"), -np.inf)):
            try:
                buf.write({"v": value})
            except Exception as exc:
                problems.append(f"{name} raised on write: {type(exc).__name__}: {exc}")
                continue
            got = buf.read()["v"]
            if got != expected:
                problems.append(f"{name} did not survive: read back {got!r}")
    finally:
        buf.close()
        _unlink_quietly(seg)
    return problems


def _w_write_one_key(seg, key, value, done_seg):
    """Write a single key into a foreign SharedDict immediately, as set_foreign_state does."""
    done = shared_memory.SharedMemory(name=done_seg)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            d = SharedDict(seg, lock=SHAREDLOCK)
            try:
                d[key] = value
            finally:
                d.close()
        done.buf[0] = 1
    except Exception:
        done.buf[0] = 2
    finally:
        done.close()


def check_deferred_writes_are_batched_and_visible():
    """`defer_writes` must batch without losing writes -- its own or a peer's (item 10).

    Five properties. The third is the one that makes deferral safe at all: the segment
    is a single blob, so flushing writes *every* key, and without a read immediately
    beforehand a minion's tick would silently revert every foreign write since its last
    refresh -- and the application calls `set_state_to` into peers' segments at 39 sites.
    """
    problems = []
    seg = "mp_defer_dict"
    done_seg = "mp_defer_done"
    _unlink_quietly(seg)
    _unlink_quietly(done_seg)
    done = shared_memory.SharedMemory(create=True, name=done_seg, size=8)
    done.buf[0] = 0
    owner = SharedDict(seg, lock=SHAREDLOCK, create=True, size=SEGMENT_SIZE)
    view = None
    try:
        owner.update({"name": "SERVO", "a": 0.0, "b": 0.0})
        owner.defer_writes(True)
        view = SharedDict(seg, lock=SHAREDLOCK)   # an independent handle: re-reads the segment

        # 1. A deferred write does not reach shared memory yet.
        owner["a"] = 1.0
        if view.get("a") != 0.0:
            problems.append(f"a deferred write was already visible to a peer: {view.get('a')!r}")
        if not owner.has_pending_writes:
            problems.append("has_pending_writes is False after a deferred write")

        # 2. ...but the writer reads its own value back immediately, despite _refresh()
        # clearing the local copy on every access.
        if owner.get("a") != 1.0:
            problems.append(f"the writer cannot see its own deferred write: {owner.get('a')!r}")

        # 3. Flushing preserves a peer's write to a different key.
        owner["a"] = 2.0
        exitcodes, stragglers = _spawn(_w_write_one_key, (seg, "b", 7.0, done_seg), n=1)
        if done.buf[0] != 1 or stragglers:
            problems.append(f"the peer writer did not complete (flag={done.buf[0]}, "
                            f"exitcodes={exitcodes})")
        owner.flush()
        after = SharedDict(seg, lock=SHAREDLOCK)
        try:
            got_a, got_b = after.get("a"), after.get("b")
        finally:
            after.close()
        if got_a != 2.0:
            problems.append(f"the deferred write did not land on flush: a={got_a!r}")
        if got_b != 7.0:
            problems.append(f"the flush reverted a peer's write to another key: b={got_b!r}")
        if owner.has_pending_writes:
            problems.append("pending survived a successful flush")

        # 4. An empty flush writes nothing and says so.
        if owner.flush() is not False:
            problems.append("flushing with nothing pending did not return False")

        # 5. A value the codec cannot represent must not wedge the flush forever. It is
        # dropped, exactly as an immediate write drops it today.
        swallowed = io.StringIO()
        owner["c"] = np.arange(3)          # unencodable: see check_failed_write_is_non_destructive
        with warnings.catch_warnings(), redirect_stdout(swallowed):
            warnings.simplefilter("ignore")
            flushed = owner.flush()
        if flushed is not False:
            problems.append("a flush that could not encode reported success")
        if "Traceback" not in swallowed.getvalue():
            problems.append("a failed flush reported nothing at all")
        if owner.has_pending_writes:
            problems.append("an unencodable value stayed pending, so every later tick "
                            "would retry it and lose its own writes too")
        owner["a"] = 3.0
        owner.flush()
        probe = SharedDict(seg, lock=SHAREDLOCK)
        try:
            if probe.get("a") != 3.0:
                problems.append(f"the segment stopped accepting writes after a failed "
                                f"flush: a={probe.get('a')!r}")
        finally:
            probe.close()

        # 6. Turning deferral off flushes rather than discarding.
        owner["a"] = 4.0
        owner.defer_writes(False)
        if view.get("a") != 4.0:
            problems.append(f"defer_writes(False) dropped a pending write: {view.get('a')!r}")
    finally:
        for handle in (view, owner):
            if handle is not None:
                try:
                    handle.close()
                except Exception:
                    pass
        done.close()
        done.unlink()
        _unlink_quietly(seg)
    return problems


# --------------------------------------------------------------------------
# known-defect checks
# --------------------------------------------------------------------------

def defect_one_reader_release_admits_writer():
    """A4 / reader count. `release_RWlock` writes ' ' with no reader count.

    Two readers hold the segment; the first to leave clears the byte outright, so
    a writer is admitted while the second reader is still inside.
    """
    seg = "mp_rc_buf"
    _unlink_quietly(seg)
    b = SharedBuffer(seg, lock=SHAREDLOCK, data={"v": 1}, size=4096, create=True)
    b._use_RWLock = True
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            if not (b.aquire_RWlock("r", timeout=100) and b.aquire_RWlock("r", timeout=100)):
                return False, "could not put two readers in"
            b.release_RWlock()  # reader A leaves; reader B is still inside
            admitted = b.aquire_RWlock("w", timeout=100)
            after = b._read_lockbyte()
        if admitted and after == "w":
            return True, "writer admitted while a reader was still holding"
        return False, f"writer not admitted (byte={after!r}) -- reader count may exist now"
    finally:
        try:
            b.close()
        except Exception:
            pass
        _unlink_quietly(seg)


def check_write_lock_excludes_concurrent_writers():
    """Two writers must never hold the write lock at once (fixed, roadmap item 15).

    `aquire_RWlock('w')` used to read the lock byte and then write it as two separate
    steps, so two processes could both observe 'free' and both proceed -- graduated out
    of `KNOWN_DEFECTS` as `lock-byte-test-and-set-is-not-atomic` now that the write-side
    transition is an atomic `cmpxchg`. Detected by stamp collision inside the critical
    section rather than by lost updates -- see `_w_guarded_marker` for why.

    Scope: writer-vs-writer only, which is what this check (and the defect it replaces)
    has ever exercised. Reader admission is unchanged and still not exclusive against a
    writer -- see `defect_one_reader_release_admits_writer`, still in `KNOWN_DEFECTS`.
    """
    problems = []
    lock_seg, marker_seg = "mp_tas_lock", "mp_tas_marker"
    _unlink_quietly(lock_seg)
    _unlink_quietly(marker_seg)
    lock = SharedBuffer(lock_seg, lock=SHAREDLOCK, data={"v": 1}, size=4096, create=True)
    marker = shared_memory.SharedMemory(create=True, name=marker_seg, size=8)
    marker.buf[0:8] = b"\x00" * 8
    procs = []
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            for i in range(N_PROC):
                p = mp.Process(
                    target=_w_guarded_marker,
                    args=(lock_seg, marker_seg, i + 1, N_ITER, 0.0005),
                )
                p.start()
                procs.append(p)
            deadline = perf_counter() + JOIN_TIMEOUT
            for p in procs:
                p.join(timeout=max(0.1, deadline - perf_counter()))
            stuck = [p for p in procs if p.is_alive()]
            for p in stuck:
                p.terminate()
                p.join(timeout=2.0)
        if stuck:
            problems.append(f"{len(stuck)} worker(s) hung")
        elif marker.buf[1] == 1:
            problems.append(
                f"two writers held the lock simultaneously "
                f"({N_PROC} processes x {N_ITER} entries, 0.5 ms hold)"
            )
    finally:
        try:
            lock.close()
        except Exception:
            pass
        marker.close()
        _unlink_quietly(lock_seg)
        _unlink_quietly(marker_seg)
    return problems


def defect_segment_outlives_owner():
    """B2. A segment stays readable, with stale content, after its owner dies.

    This is why `is_alive()` keeps returning True for a crashed minion and why
    `AbstractGUIAPP.shutdown()`'s unbounded loop never terminates. It is also
    exactly what the heartbeat vector in roadmap item 11 is for: liveness has to
    come from observed progress, not from the segment's existence.
    """
    seg, ready_seg = "mp_orphan", "mp_orphan_ready"
    _unlink_quietly(seg)
    _unlink_quietly(ready_seg)
    ready = shared_memory.SharedMemory(create=True, name=ready_seg, size=8)
    ready.buf[0:8] = b"\x00" * 8
    peer = None
    proc = mp.Process(target=_w_create_attach_then_die, args=(seg, ready_seg))
    proc.start()
    try:
        for _ in range(500):                      # wait for the segment to exist
            if ready.buf[0] == 1:
                break
            sleep(0.01)
        if ready.buf[0] != 1:
            return False, "worker never created the segment"
        peer = shared_memory.SharedMemory(name=seg)   # attach, as a linked minion does
        ready.buf[1] = 1                              # release the worker to die
        proc.join(timeout=JOIN_TIMEOUT)
        if proc.is_alive():
            return False, "worker did not exit"

        value = int.from_bytes(bytes(peer.buf[0:4]), "little")
        if value == 12345:
            return True, (
                f"owner exited (code={proc.exitcode}) yet the attached peer still reads "
                "its last value; nothing marks it dead"
            )
        return False, f"peer read unexpected content ({value})"
    finally:
        if proc.is_alive():
            proc.terminate()
            proc.join(timeout=2.0)
        if peer is not None:
            peer.close()
        ready.close()
        _unlink_quietly(ready_seg)
        _unlink_quietly(seg)


def defect_terminate_after_close_raises():
    """`terminate()` dereferences `_shared_memory` after `close()` set it to None."""
    seg = "mp_term_buf"
    _unlink_quietly(seg)
    b = SharedBuffer(seg, lock=SHAREDLOCK, data={"v": 1}, size=4096, create=True)
    b.close()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            b.terminate()
    except TypeError as exc:
        return True, f"{type(exc).__name__}: {exc}"
    except Exception as exc:
        return False, f"raised {type(exc).__name__} instead of TypeError: {exc}"
    finally:
        _unlink_quietly(seg)
    return False, "terminate() after close() no longer raises"


DEFECT_CHECKS = {
    "A4-one-reader-release-admits-a-writer": defect_one_reader_release_admits_writer,
    "B2-segment-outlives-its-owner": defect_segment_outlives_owner,
    "terminate-after-close-raises": defect_terminate_after_close_raises,
}


# --------------------------------------------------------------------------
# performance (opt-in)
# --------------------------------------------------------------------------

def _w_write_loop(name, iters):
    d = SharedDict(name, lock=SHAREDLOCK)
    try:
        for i in range(iters):
            d["counter"] = i
    finally:
        d.close()


# --- contended write measurement (roadmap item 10) -------------------------
#
# The single-process figure for batching is an uncontended upper bound, and this
# project has a standing record of getting system behaviour wrong by inferring it
# from a microbenchmark. What the decision actually needs is the cost with peers
# hammering the same segment, on both sides: what the owner pays per tick, and what
# its readers pay while it writes.
#
# Phases are driven by a control byte so that owner and readers agree on which
# regime each sample belongs to. Readers bucket their own timings by that byte.
CONTROL_IDLE, CONTROL_PER_KEY, CONTROL_BATCHED, CONTROL_DEFERRED, CONTROL_STOP = 0, 1, 2, 3, 4
PHASE_NAMES = {CONTROL_IDLE: "owner idle", CONTROL_PER_KEY: "owner writes per key",
               CONTROL_BATCHED: "owner writes batched (modelled)",
               CONTROL_DEFERRED: "owner writes deferred (real path)"}
MEASURED_PHASES = (CONTROL_IDLE, CONTROL_PER_KEY, CONTROL_BATCHED, CONTROL_DEFERRED)
_SLOT_BYTES = 8 * 2 * len(MEASURED_PHASES)

# SERVO's real shape: 19 keys, 12 of them rewritten every tick at a 1 ms interval.
SERVO_KEYS = [f"dynamotor_{axis}" for axis in ("x", "y", "z")] + \
             [f"torque_{axis}" for axis in ("x", "y", "z")] + \
             ["cmd_idx", "pin_1", "pin_2", "param_1", "param_2", "param_3"]
SERVO_PADDING = {f"cfg_{i}": f"value_{i}" for i in range(6)}
OWNER_TICK = 0.001


def _w_contended_reader(seg, control_seg, result_seg, slot):
    """Read the owner's segment the way get_foreign_state does, bucketed by phase.

    Writes six doubles into its slot: (total_s, count) for each of the three phases.
    """
    import struct

    control = shared_memory.SharedMemory(name=control_seg)
    result = shared_memory.SharedMemory(name=result_seg)
    totals = [0.0] * len(MEASURED_PHASES)
    counts = [0] * len(MEASURED_PHASES)
    try:
        d = SharedDict(seg, lock=SHAREDLOCK)
        try:
            while True:
                phase = control.buf[0]
                if phase == CONTROL_STOP:
                    break
                t0 = perf_counter()
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    if "cmd_idx" in d.keys():
                        d["cmd_idx"]
                dt = perf_counter() - t0
                # Re-read the phase: a sample that straddled a transition belongs to
                # neither bucket, so drop it rather than attribute it to the wrong one.
                if control.buf[0] == phase and phase != CONTROL_STOP:
                    totals[phase] += dt
                    counts[phase] += 1
        finally:
            d.close()
    except Exception:
        pass
    finally:
        try:
            flat = []
            for phase in MEASURED_PHASES:
                flat += [totals[phase], float(counts[phase])]
            packed = struct.pack(f"{len(flat)}d", *flat)
            result.buf[slot * _SLOT_BYTES:(slot + 1) * _SLOT_BYTES] = packed
        except Exception:
            pass
        control.close()
        result.close()


def _set_state_equivalent(d, key, val):
    """Exactly what BaseMinion.set_state does for a plain dict-valued state.

    Two full refreshes and one full re-encode per key: `key in d.keys()` is one
    `_refresh()`, `d[key]` (the `b*` prefix test) is a second, and the assignment
    re-serialises the whole dict.
    """
    if key in d.keys():
        stored = d[key]
        if not (isinstance(stored, str) and stored.startswith("b*")):
            d[key] = val


def measure_contended_writes(n_readers=3, phase_s=1.5):
    """Owner and reader cost per regime, with `n_readers` peers reading throughout.

    The owner is paced at a real 1 ms tick rather than writing back to back, so the
    reader figures reflect a realistic duty cycle instead of a saturated segment.

    Caveat that limits what these numbers can settle: the RW lock is still the broken
    one (`KNOWN_DEFECTS` holds both the missing reader count and the non-atomic
    test-and-set), so a reader releasing it frees it for everyone. Real contention with
    a *correct* lock would be higher than measured here, which pushes the same way as
    the acquisition counts below rather than against them.
    """
    import struct

    seg, control_seg, result_seg = "mp_cont_dict", "mp_cont_ctl", "mp_cont_res"
    for name in (seg, control_seg, result_seg):
        _unlink_quietly(name)

    control = shared_memory.SharedMemory(create=True, name=control_seg, size=8)
    result = shared_memory.SharedMemory(create=True, name=result_seg,
                                        size=_SLOT_BYTES * n_readers)
    control.buf[0] = CONTROL_IDLE
    result.buf[:] = b"\x00" * len(result.buf)

    owner = SharedDict(seg, lock=SHAREDLOCK, create=True, size=SEGMENT_SIZE)
    procs = []
    out = {"readers": {}, "owner": {}, "n_readers": n_readers}
    try:
        owner.update({"name": "SERVO", **{k: 0.0 for k in SERVO_KEYS}, **SERVO_PADDING})
        buf = owner._linked_SharedBuffer

        procs = [mp.Process(target=_w_contended_reader,
                            args=(seg, control_seg, result_seg, i))
                 for i in range(n_readers)]
        for p in procs:
            p.start()
        sleep(0.5)  # let every reader attach before the first timed phase

        def run_phase(phase, tick_body):
            control.buf[0] = phase
            total, ticks = 0.0, 0
            deadline = perf_counter() + phase_s
            while perf_counter() < deadline:
                next_tick = perf_counter() + OWNER_TICK
                if tick_body is not None:
                    t0 = perf_counter()
                    tick_body()
                    total += perf_counter() - t0
                    ticks += 1
                while perf_counter() < next_tick:   # pace like TimerMinion: spin
                    pass
            return (total / ticks * 1e6) if ticks else None

        def per_key_tick():
            for i, key in enumerate(SERVO_KEYS):
                _set_state_equivalent(owner, key, float(i))

        def batched_tick():
            """The projection: refresh, overlay every key, write once."""
            owner._refresh()
            local = dict(owner)
            for i, key in enumerate(SERVO_KEYS):
                local[key] = float(i)
            buf.write(local)

        def deferred_tick():
            """The real path: BaseMinion.set_state x12, then innerLoop's flush."""
            for i, key in enumerate(SERVO_KEYS):
                if key in owner.local_keys():
                    stored = owner.local_get(key)
                    if not (isinstance(stored, str) and stored.startswith("b*")):
                        owner[key] = float(i)
            owner.flush()

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            run_phase(CONTROL_IDLE, None)
            out["owner"][CONTROL_PER_KEY] = run_phase(CONTROL_PER_KEY, per_key_tick)
            out["owner"][CONTROL_BATCHED] = run_phase(CONTROL_BATCHED, batched_tick)
            owner.defer_writes(True)
            try:
                out["owner"][CONTROL_DEFERRED] = run_phase(CONTROL_DEFERRED, deferred_tick)
            finally:
                owner.defer_writes(False)
        control.buf[0] = CONTROL_STOP

        deadline = perf_counter() + JOIN_TIMEOUT
        for p in procs:
            p.join(timeout=max(0.1, deadline - perf_counter()))

        for slot in range(n_readers):
            vals = struct.unpack(f"{2 * len(MEASURED_PHASES)}d",
                                 bytes(result.buf[slot * _SLOT_BYTES:(slot + 1) * _SLOT_BYTES]))
            for phase in MEASURED_PHASES:
                total, count = vals[phase * 2], vals[phase * 2 + 1]
                if count:
                    out["readers"].setdefault(phase, []).append(total / count * 1e6)
    finally:
        for p in procs:
            if p.is_alive():
                p.terminate()
                p.join(timeout=2.0)
        owner.close()
        control.close()
        result.close()
        for name in (seg, control_seg, result_seg):
            _unlink_quietly(name)
    return out


def report_contended_writes(out):
    n = out["n_readers"]
    lines = [f"Contended write cost -- SERVO's shape (19 keys, {len(SERVO_KEYS)} rewritten "
             f"per 1 ms tick), {n} peers reading throughout:", ""]
    per_key = out["owner"].get(CONTROL_PER_KEY)
    batched = out["owner"].get(CONTROL_BATCHED)
    lines.append(f"  owner, per-key writes (as today)      {per_key:8.2f} us per tick"
                 if per_key else "  owner, per-key writes: no samples")
    lines.append(f"  owner, batched (modelled)             {batched:8.2f} us per tick"
                 if batched else "  owner, batched: no samples")
    deferred = out["owner"].get(CONTROL_DEFERRED)
    lines.append(f"  owner, deferred (real path)           {deferred:8.2f} us per tick"
                 if deferred else "  owner, deferred: no samples")
    if per_key and batched:
        lines.append(f"  ratio, modelled                       {per_key / batched:8.1f}x")
    if per_key and deferred:
        lines.append(f"  ratio, real                           {per_key / deferred:8.1f}x")
    lines.append("")
    lines.append(f"  reader cost ({n} peers, mean of their means):")
    for phase in MEASURED_PHASES:
        vals = out["readers"].get(phase)
        if vals:
            lines.append(f"    {PHASE_NAMES[phase]:<34}{sum(vals) / len(vals):8.2f} us per read")
    lines.append("")
    lines.append(f"  lock acquisitions per tick: {3 * len(SERVO_KEYS)} per-key "
                 f"({len(SERVO_KEYS)} x 2 reads + {len(SERVO_KEYS)} writes) vs 2 batched. "
                 f"At today's 1.71 us that is minor; at\n  the 15.7 us a correct "
                 f"`atomics` CAS costs (roadmap item 15) it is "
                 f"{3 * len(SERVO_KEYS) * 15.7:.0f} us vs {2 * 15.7:.0f} us per tick.")
    return "\n".join(lines)


def measure_round_trip(iters=1000):
    """Cost of a foreign read and of an owner write, as the framework performs them."""
    seg = "mp_perf_dict"
    _unlink_quietly(seg)
    owner = SharedDict(seg, lock=SHAREDLOCK, create=True, size=SEGMENT_SIZE)
    out = {}
    try:
        owner["name"] = "PERF"
        owner["timestamp"] = 1764328094123.456
        owner["counter"] = 0

        t0 = perf_counter()
        for _ in range(iters):
            owner["counter"] = 1
        out["own write (us)"] = (perf_counter() - t0) / iters * 1e6

        peer = SharedDict(seg, lock=SHAREDLOCK)
        t0 = perf_counter()
        for _ in range(iters):
            peer.get("timestamp")
        out["foreign read, 1 refresh (us)"] = (perf_counter() - t0) / iters * 1e6

        # get_foreign_state does `key in d.keys()` and then `d[key]`: two refreshes
        t0 = perf_counter()
        for _ in range(iters):
            if "timestamp" in peer.keys():
                peer["timestamp"]
        out["foreign read, as framework does (us)"] = (perf_counter() - t0) / iters * 1e6
        peer.close()

        t0 = perf_counter()
        _spawn(_w_write_loop, (seg, iters), n=1)
        out["contended writer, wall clock (s)"] = perf_counter() - t0
    finally:
        owner.close()
        _unlink_quietly(seg)
    return out


# --------------------------------------------------------------------------
# pytest entry points
# --------------------------------------------------------------------------

def test_cross_process_visibility():
    problems = check_cross_process_visibility()
    assert not problems, "; ".join(problems)


def test_dynamic_declaration():
    problems = check_dynamic_declaration()
    assert not problems, "; ".join(problems)


def test_failed_write_is_non_destructive():
    problems = check_failed_write_is_non_destructive()
    assert not problems, "; ".join(problems)


def test_header_release_requires_acquire():
    problems = check_header_release_requires_acquire()
    assert not problems, "; ".join(problems)


def test_write_lock_excludes_concurrent_writers():
    problems = check_write_lock_excludes_concurrent_writers()
    assert not problems, "; ".join(problems)


def test_payload_framing_is_length_prefixed():
    problems = check_payload_framing_is_length_prefixed()
    assert not problems, "; ".join(problems)


def test_deferred_writes_are_batched_and_visible():
    problems = check_deferred_writes_are_batched_and_visible()
    assert not problems, "; ".join(problems)


def test_numpy_scalars_survive_a_real_write():
    problems = check_numpy_scalars_survive_a_real_write()
    assert not problems, "; ".join(problems)


def test_generation_counter_tracks_every_write():
    problems = check_generation_counter_tracks_every_write()
    assert not problems, "; ".join(problems)


def test_known_defects_still_reproduce():
    """Fails when a baseline defect stops reproducing, so the baseline cannot rot."""
    stale = []
    for name in sorted(KNOWN_DEFECTS):
        reproduced, detail = DEFECT_CHECKS[name]()
        if not reproduced:
            stale.append(f"{name}: {detail}")
    assert not stale, (
        "baseline entries no longer reproduce -- if this is a fix, remove them from "
        "KNOWN_DEFECTS:\n  " + "\n  ".join(stale)
    )


if __name__ == "__main__":
    mp.freeze_support()
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    print(f"python {sys.version.split()[0]} | {N_PROC} processes | numpy {np.__version__}")

    failed = False
    for label, fn in (
        ("cross-process visibility", check_cross_process_visibility),
        ("dynamic declaration after attach", check_dynamic_declaration),
        ("failed write is non-destructive (B1)", check_failed_write_is_non_destructive),
        ("header release requires acquire (C10)", check_header_release_requires_acquire),
        ("write lock excludes concurrent writers (item 15)", check_write_lock_excludes_concurrent_writers),
        ("payload framing is length-prefixed (item 9)", check_payload_framing_is_length_prefixed),
        ("deferred writes are batched and visible (item 10)",
         check_deferred_writes_are_batched_and_visible),
        ("numpy scalars survive a real write (item 11)",
         check_numpy_scalars_survive_a_real_write),
        ("generation counter tracks every write (item 14)",
         check_generation_counter_tracks_every_write),
    ):
        problems = fn()
        if problems:
            failed = True
            print(f"FAIL {label}")
            for p in problems:
                print(f"       {p}")
        else:
            print(f"OK   {label}")

    print("\nKnown defects (each must still reproduce until its fix lands):")
    stale = []
    for name in sorted(KNOWN_DEFECTS):
        reproduced, detail = DEFECT_CHECKS[name]()
        mark = "repro" if reproduced else "GONE "
        print(f"  {mark}  {name}\n         {detail}")
        if not reproduced:
            stale.append(name)
    if stale:
        failed = True
        print(
            f"\nFAIL {len(stale)} baseline entry/entries no longer reproduce. If that is "
            "a fix, remove them from KNOWN_DEFECTS."
        )
    else:
        print(f"\nOK   known defects: all {len(KNOWN_DEFECTS)} still reproduce")

    if "--perf" in sys.argv:
        print("\nCost of the framework's own access patterns:")
        for k, v in measure_round_trip().items():
            unit = "" if k.endswith("(s)") else ""
            print(f"  {k:<40} {v:8.2f}{unit}")

        print()
        print(report_contended_writes(measure_contended_writes()))

    raise SystemExit(1 if failed else 0)
