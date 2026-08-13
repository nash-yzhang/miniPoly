"""Correctness and speed of the SharedDict serialisation codec.

`SharedBuffer.write` / `.read` ([core/buffer.py]) encode the whole `SharedDict` on
every write and decode it on every read, using stdlib `json` plus a `default` hook
for numpy scalars (roadmap item 11). Two questions follow, and this module answers
both with the real payloads the application actually puts in shared memory:

1. **Correctness** -- which value types survive a round trip with their type
   intact? The schema-free namespace means the type is carried by the value, and
   `dockableGUI._update_surveillance_state_list` dispatches on `type(val)` read
   back out of shared memory, so a codec that silently changes a type changes
   application behaviour.
2. **Cost** -- how expensive is the codec itself, and does a faster one exist that
   does not give up the schema-free property (i.e. needs no declared schema)?

**Both are settled (roadmap items 9-11); this module is the record of why.** The answer
to question 2 turned out to be "yes, and none of them is usable here" -- every faster
candidate lost on question 1. The three rejections are set out below and pinned by
`check_numpy_scalars`, `check_non_finite_floats` and `check_python_types`.

The `json + hook (current)` row is imported from `core/buffer.py` rather than rebuilt
here, so the table cannot drift away from what the library really does.

> **Scope warning, and it matters.** The timings here are for the **codec alone**:
> `dumps` and `loads` on an in-memory dict. They are *not* the cost of
> `SharedBuffer.read` / `.write`, and they are not the cost of `get_state_from`.
>
> The ranking these numbers produced was: **replace the NUL terminator with a length
> prefix first**, and treat the codec swap as a **correctness** change -- it removes
> B1's realistic trigger -- rather than a performance one. That first half is now
> done (roadmap item 9). Before it, the codec was ~2 % of a foreign read and the other
> 98 % was ``bytes(buf[...]).decode('utf-8').split('\\x00')[0]``, which scaled with the
> *segment* size rather than the payload -- on an 8 KB segment holding a 94 B payload
> the split allocated ~8 000 string objects:
>
> | segment | `read()` before | of which `split('\\x00')` | length-prefixed, now |
> |---|---|---|---|
> | 8192 B | 85.4 us | 79.8 us (93 %) | **3.1 us** |
> | 2048 B | 28.2 us | 25.1 us | 3.3 us |
> | 512 B | 11.0 us | 8.2 us | 3.3 us |
>
> Measured end to end in
> [tests/test_core_multiprocess.py](tests/test_core_multiprocess.py) `--perf`, the
> foreign read the framework really performs went from **118.6 us to 7.5 us**, and a
> SERVO tick's writes from 1054 us to 21 us (item 10). So the codec's share of both
> paths has risen sharply -- it is now roughly a third of a read, and about half of a
> flush -- and this module's timings matter proportionally more than they did.
>
> **That did not change item 11's outcome, but it did change the reasoning.** The
> decision was never about the ~2 %: it is that `orjson` and `msgspec-json` both encode
> NaN and +-Infinity as `null`, so those values return as `None`. See
> `check_non_finite_floats` for why that is reachable here and what it breaks. The
> numpy correctness half was taken instead by giving stdlib json a `default` hook,
> which costs nothing on payloads that contain no numpy values.

Provenance of the payloads: the state names, types and magnitudes below are taken
from one real recording session on the rig (2025-11-28, `animal_id` "test123") plus
the `create_state` / `create_shared_buffer` call sites in miniPoly and CaImg_App.
The session's own CSVs, `_INFO.json` and log are deliberately **not** in this
repository -- they carry the rig's network identity and a colleague's unpublished
protocol names -- so every value they contributed is transcribed literally into the
dicts below and is self-contained here. Values that only ever appear as a
`b*`-prefixed reference to a `SharedNdarray` are represented as such, because that
is what is really in the dict.

Notes on what is NOT in these payloads:

- `watch_state` values live in `BaseMinion._watching_state`, a plain local dict,
  so they never reach the segment.
- `create_streaming_state(..., shared=False)` states are local too. `protocolFn`
  on SERVO is one of these: it appears as a CSV column but not in the dict.

Standalone:  python tests/test_serialization.py
             python tests/test_serialization.py --bench      (adds timings)
pytest:      pytest tests/test_serialization.py
"""

import json
import pickle
import sys

import numpy as np

# `_INDEX_SHARED_BUFFER_SIZE` in core/minion.py, minus SharedBuffer's header. That
# is `_READ_OFFSET` (len(_CLASS_NAME) + 1, and 'SharedBuffer' is 12 characters) plus
# `_LOCK_OFFSET` (1) plus `_LENGTH_OFFSET` (4, the payload length added by roadmap
# item 9), i.e. 18 bytes unavailable.
SEGMENT_SIZE = 2 ** 13
USABLE_BYTES = SEGMENT_SIZE - (len("SharedBuffer") + 1) - 1 - 4


# --------------------------------------------------------------------------
# The real payloads
# --------------------------------------------------------------------------

# These two are long strings that dominate the GUI and camera payload sizes, so what
# this module measures is their *length*, not their content. The rig's real protocol
# path is 58 characters; the stand-in below matches that exactly but is synthetic,
# because the real one names a colleague's unpublished experiment. Keep the length if
# you ever change it, or the size figures stop describing the real payload.
_PROTOCOL_PATH = "D:/protocols/synthetic_openloop_protocol_rep03_251125.xlsx"
_SAVE_DIR = "D:\\data\\/20251128_122814"
_SAVE_NAME = "20251128_122814"
_VIDEO_FORMAT = "Y800 (744x480)"

# refresh_interval per minion, from CaImg_App/app_setter/VR_init.py. Used to
# weight the aggregate cost estimate.
TICK_MS = {"SCAN": 1, "OMS": 1, "SERVO": 1, "GUI": 1, "Cam1": 20, "Cam2": 20, "Cam3": 20}

REAL_PAYLOADS = {
    # ScanListener: the time base. `timestamp` is created with use_buffer=False,
    # which is why every other minion's get_state_from('SCAN', 'timestamp') pays
    # for a full decode of this dict once per tick.
    "SCAN": {
        "name": "SCAN",
        "status": "b*SCAN_status",
        "timestamp": 1764328094123.456,
        "ca_frame_num": 0,
    },
    # OMSDuo: seven float states, all produced by np.nanmean -> np.float64.
    # Magnitudes copied from the 2025-11-28 session's OMS stream, row 1.
    "OMS": {
        "name": "OMS",
        "status": "b*OMS_status",
        "sR": -0.2148235294117648,
        "sX": 0.025411764705882346,
        "sY": 0.16603921568627455,
        "M1x": -0.12376470588235294,
        "M1y": 0.025411764705882346,
        "M2x": -0.30588235294117666,
        "M2y": 0.16603921568627455,
    },
    # AzimuthCloseloopCompiler: the largest dict in the topology, and therefore
    # the one nearest the segment ceiling. Names come from the motor_dict keys in
    # VR_init.py; values from the 2025-11-28 session's SERVO stream, row 1.
    "SERVO": {
        "name": "SERVO",
        "status": "b*SERVO_status",
        "cmd_idx": "b*SERVO_cmd_idx",
        "serial_cmd": "",
        "dynamixel_cmd": "",
        "compiler_cmd": "",
        "motor_names": ["dynamotor_x", "dynamotor_y", "dynamotor_z"],
        "dynamotor_x": 94.82707747456773,
        "dynamotor_y": 82.3723323538407,
        "dynamotor_z": -0.0019999999999988916,
        "dynamotor_x_torque": 1,
        "dynamotor_y_torque": 1,
        "dynamotor_z_torque": 1,
        "light_pin": 0,
        "mask_servo": 120,
        "flag_servo": 25,
        "lclv_pin": 0,
        "CLGAIN": 0,
        "EPISODE": 0,
    },
    # DynamotorGUI: the trigger minion. Long path strings dominate the size.
    "GUI": {
        "name": "GUI",
        "status": "b*GUI_status",
        "runSignal": "b*GUI_runSignal",
        "StreamToDisk": "b*GUI_StreamToDisk",
        "protocolFn": _PROTOCOL_PATH,
        "SaveDir": _SAVE_DIR,
        "SaveName": _SAVE_NAME,
        "AnimalID": "test123",
        "StreamingDevices": ["Cam1", "Cam2", "Cam3"],
    },
    # TISCameraCompiler. The frame buffer's dict key is built from the video
    # format at runtime -- see the 'Unknown foreign state
    # frame_Y800_(744x480)' errors in the 2025-11-28 session log.
    "Cam1": {
        "name": "Cam1",
        "status": "b*Cam1_status",
        "CameraName": "DMK 33UX287 12345678",
        "VideoFormat": _VIDEO_FORMAT,
        "SaveDir": _SAVE_DIR,
        "SaveName": _SAVE_NAME,
        "StreamToDisk": False,
        "InitTime": 0.0,
        f"frame_{_VIDEO_FORMAT}": f"b*Cam1_frame_{_VIDEO_FORMAT}",
    },
}


# --------------------------------------------------------------------------
# Codecs
#
# Every candidate must be schema-free: it has to encode an arbitrary dict with
# arbitrary string keys and heterogeneous values, with no declared type. That
# rules out msgspec's Struct path (its fastest mode) but not its untyped one.
# --------------------------------------------------------------------------

def _make_codecs():
    codecs = {}

    # What core/buffer.py actually uses since roadmap item 11: stdlib json with a
    # `default` hook that sends numpy scalars through `.item()`. Imported rather than
    # reconstructed, so this row cannot drift away from the real encoder.
    from miniPoly.core.buffer import _encode as _buffer_encode

    codecs["json + hook (current)"] = (
        _buffer_encode,
        lambda b: json.loads(b),
        "text",
    )

    # The bare codec, kept for the comparison: it is what the hook is protecting
    # against, and the numpy row below is the whole reason the hook exists.
    codecs["json (bare stdlib)"] = (
        lambda o: json.dumps(o).encode("utf-8"),
        lambda b: json.loads(b.decode("utf-8")),
        "text",
    )

    try:
        import orjson

        opt = orjson.OPT_SERIALIZE_NUMPY
        codecs["orjson"] = (lambda o: orjson.dumps(o, option=opt), orjson.loads, "text")
    except ImportError:
        pass

    try:
        import msgspec

        je, jd = msgspec.json.Encoder(), msgspec.json.Decoder()
        codecs["msgspec-json"] = (je.encode, jd.decode, "text")
        me, md = msgspec.msgpack.Encoder(), msgspec.msgpack.Decoder()
        codecs["msgspec-msgpack"] = (me.encode, md.decode, "binary")
    except ImportError:
        pass

    codecs["pickle-v5"] = (
        lambda o: pickle.dumps(o, protocol=5),
        pickle.loads,
        "binary",
    )
    return codecs


CODECS = _make_codecs()

# numpy scalar types that reach a state value. OMSDuo's states come out of
# np.nanmean (float64); a dtype= change anywhere upstream would substitute
# another of these.
NUMPY_SCALARS = {
    "float64": np.float64(1.5),
    "float32": np.float32(1.5),
    "float16": np.float16(1.5),
    "int64": np.int64(7),
    "int32": np.int32(7),
    "int8": np.int8(7),
    "uint64": np.uint64(7),
    "bool_": np.bool_(True),
}

# Python types that must survive with their type unchanged, because
# `_update_surveillance_state_list` and `set_state`'s `b*` detection both
# dispatch on type().
PYTHON_TYPES = {
    "int": 7,
    "float": 1.5,
    "bool": True,
    "str": "abc",
    "NoneType": None,
    "list": [1, 2, 3],
    "tuple": (1, 2, 3),
    "dict": {"a": 1},
}


def _round_trip(codec, obj):
    enc, dec, _ = codec
    return dec(enc(obj))


# --------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------

def check_real_payloads():
    """Every real payload must round trip through every codec, value and type."""
    problems = []
    for name, codec in CODECS.items():
        for minion, payload in REAL_PAYLOADS.items():
            try:
                out = _round_trip(codec, payload)
            except Exception as exc:
                problems.append(f"{name}: {minion} failed to encode: {exc!r}")
                continue
            if out != payload:
                problems.append(f"{name}: {minion} value changed across the round trip")
                continue
            for key, val in payload.items():
                if type(out[key]) is not type(val):
                    problems.append(
                        f"{name}: {minion}[{key!r}] type {type(val).__name__} "
                        f"-> {type(out[key]).__name__}"
                    )
    return problems


def check_python_types():
    """Report, per codec, which Python types do not survive as the same type."""
    table = {}
    for name, codec in CODECS.items():
        row = {}
        for tname, val in PYTHON_TYPES.items():
            try:
                out = _round_trip(codec, {"v": val})["v"]
            except Exception as exc:
                row[tname] = f"raise {type(exc).__name__}"
                continue
            if type(out) is not type(val):
                row[tname] = f"-> {type(out).__name__}"
            elif out != val:
                row[tname] = "value changed"
            else:
                row[tname] = "ok"
        table[name] = row
    return table


def check_numpy_scalars():
    """Report, per codec, which numpy scalar types can be encoded at all."""
    table = {}
    for name, codec in CODECS.items():
        row = {}
        for tname, val in NUMPY_SCALARS.items():
            try:
                out = _round_trip(codec, {"v": val})["v"]
            except Exception as exc:
                row[tname] = f"raise {type(exc).__name__}"
                continue
            row[tname] = "ok" if type(out) is type(val) else f"-> {type(out).__name__}"
        table[name] = row
    return table


def check_sizes():
    """Encoded size of each real payload against the usable segment size."""
    rows = {}
    for minion, payload in REAL_PAYLOADS.items():
        rows[minion] = {n: len(c[0](payload)) for n, c in CODECS.items()}
    return rows


def check_non_finite_floats():
    """Does a codec preserve NaN and +-Infinity, or silently turn them into something else?

    This is the property that decided roadmap item 11, and it is not visible anywhere
    else in this module's tables. `orjson` encodes NaN and +-Infinity as `null`, so they
    come back as **None**. That is reachable in this application: OMS builds its rotation
    states through `np.nanmean`, which returns NaN for an all-NaN window, and
    `dockableGUI.rotate_sphere` then calls `np.isnan(r)` on one of them -- which raises
    TypeError for None rather than skipping the frame. Protocol spreadsheets are another
    source: `pd.read_excel` yields NaN for an empty cell, and `closelooper.py` calls
    `fillna` on only two of its columns.

    stdlib json emits the bare tokens `NaN` / `Infinity`, which are **not valid JSON**
    per RFC 8259 -- that is why orjson refuses to -- but it round-trips them through its
    own loader, and nothing outside this library ever parses these segments. So the
    invalid-JSON objection does not apply here, and the round trip does.
    """
    rows = {}
    for name, codec in CODECS.items():
        enc, dec, _ = codec
        results = {}
        for label, value in (("nan", float("nan")), ("+inf", float("inf")),
                             ("-inf", float("-inf"))):
            try:
                back = dec(enc({"v": value}))["v"]
            except Exception as exc:
                results[label] = f"raise {type(exc).__name__}"
                continue
            if isinstance(back, float) and np.isnan(back):
                results[label] = "nan"
            elif back is None:
                results[label] = "-> None"
            else:
                results[label] = repr(back)
        rows[name] = results
    return rows


def check_nul_safety():
    """Whether a codec's output can contain a NUL byte. No longer disqualifying.

    `SharedBuffer.read` used to recover the payload with
    ``bytes(buf[...]).decode('utf-8').split('\\x00')[0]``, treating the first NUL as
    end-of-data, so any codec whose output could contain one was ruled out. Roadmap
    item 9 replaced that with an explicit length prefix, which lifts the constraint --
    this check is now informational, and a binary codec is admissible on this axis.

    Note that it never bound the *current* codec: `json.dumps` escapes NUL in a value
    to ``\\u0000``, so its output cannot contain a literal NUL byte. The constraint was
    always about which codecs item 11 could choose from, never about which values the
    framework could store.
    """
    unsafe = {}
    for name, codec in CODECS.items():
        hits = [m for m, p in REAL_PAYLOADS.items() if b"\x00" in codec[0](p)]
        if hits:
            unsafe[name] = hits
    return unsafe


# --------------------------------------------------------------------------
# pytest entry points
# --------------------------------------------------------------------------

def test_real_payloads_round_trip():
    problems = check_real_payloads()
    assert not problems, "codec round-trip problems:\n  " + "\n  ".join(problems)


def test_current_codec_rejects_non_float64_numpy():
    """Pin the hazard the `default` hook exists to absorb, and that the hook absorbs it.

    `np.float64` subclasses Python `float`, so **bare** stdlib json accepts it by
    accident and rejects every other numpy scalar type. Every OMS and motor state is
    numpy-derived, so a `dtype=` change upstream turned into a raise inside
    `SharedBuffer.write`.

    Both halves are asserted here: the bare codec still rejects them -- so the hook is
    load-bearing and removing it would reopen B1's trigger -- and the encoder the
    library actually uses accepts all eight (roadmap item 11).

    The raise was already made non-destructive earlier: Stage 1 item 1 moved the encode
    ahead of the lock and item 9 removed the zero-fill, so a rejected value left the
    previous payload readable and the lock byte free. The state simply never updated,
    silently, which is what item 11 closed.
    """
    enc = CODECS["json (bare stdlib)"][0]
    assert enc({"v": np.float64(1.5)})
    for tname in ("float32", "int64", "int32", "bool_"):
        try:
            enc({"v": NUMPY_SCALARS[tname]})
        except TypeError:
            continue
        raise AssertionError(f"stdlib json unexpectedly accepted np.{tname}")

    # ...and the encoder the library actually uses takes all of them.
    live = CODECS["json + hook (current)"][0]
    for tname, value in NUMPY_SCALARS.items():
        try:
            live({"v": value})
        except Exception as exc:
            raise AssertionError(
                f"the buffer encoder rejected np.{tname}: {type(exc).__name__}: {exc}"
            )


def test_current_codec_preserves_non_finite_floats():
    """Pin the property that rejected orjson for item 11. See check_non_finite_floats."""
    rows = check_non_finite_floats()["json + hook (current)"]
    assert rows["nan"] == "nan", f"NaN did not survive the round trip: {rows['nan']}"
    assert rows["+inf"] == "inf", f"+Infinity did not survive: {rows['+inf']}"
    assert rows["-inf"] == "-inf", f"-Infinity did not survive: {rows['-inf']}"


def test_real_payloads_fit_the_segment():
    for minion, sizes in check_sizes().items():
        got = sizes["json + hook (current)"]
        assert got < USABLE_BYTES, (
            f"{minion} encodes to {got} B, over the {USABLE_BYTES} B usable in an "
            f"{SEGMENT_SIZE} B segment"
        )


# --------------------------------------------------------------------------
# Benchmark
# --------------------------------------------------------------------------

def benchmark(repeat=20000):
    import timeit

    results = {}
    for name, codec in CODECS.items():
        enc, dec, _ = codec
        per_codec = {}
        for minion, payload in REAL_PAYLOADS.items():
            try:
                blob = enc(payload)
            except Exception:
                per_codec[minion] = None
                continue
            n = max(1000, repeat // len(REAL_PAYLOADS))
            t_enc = timeit.timeit(lambda: enc(payload), number=n) / n
            t_dec = timeit.timeit(lambda: dec(blob), number=n) / n
            per_codec[minion] = (t_enc * 1e6, t_dec * 1e6)
        results[name] = per_codec
    return results


def aggregate_read_cost(results):
    """Decode cost per second of steady state, as VR_init.py is configured.

    Every minion reads SCAN's `timestamp` once per tick (`get_timestamp`), which
    decodes SCAN's whole dict. That single pattern is the dominant read load, so
    it is the one worth pricing.
    """
    reads_per_sec = sum(1000.0 / ms for ms in TICK_MS.values())
    out = {}
    for name, per_codec in results.items():
        scan = per_codec.get("SCAN")
        if scan is None:
            continue
        out[name] = (reads_per_sec, scan[1] * reads_per_sec / 1e6 * 100.0)
    return out, reads_per_sec


# How many of its own states each minion writes per tick, and how many foreign
# reads it performs. Counted from the on_time / _update_states paths:
#   OMS._update_states   -> 7 set_streaming_state calls
#   SERVO (dynamixel)    -> 3 distance + 3 torque + 6 pin/param states
#   SCAN                 -> timestamp + ca_frame_num
#   Cam                  -> FrameCount is a local streaming state; only the
#                           preview buffer is shared, so no dict write per frame
# Foreign reads: get_timestamp() every tick, plus the trigger-minion polls in
# _streaming_setup (StreamToDisk) and the protocol path.
WRITES_PER_TICK = {"SCAN": 2, "OMS": 7, "SERVO": 12, "GUI": 1, "Cam1": 0, "Cam2": 0, "Cam3": 0}
FOREIGN_READS_PER_TICK = {"SCAN": 1, "OMS": 2, "SERVO": 3, "GUI": 2, "Cam1": 2, "Cam2": 2, "Cam3": 2}

# `SharedDict.__getitem__`, `.get()` and `.keys()` each call `_refresh()`, which
# is one full decode. `get_foreign_state` does `state_name in shared_dict.keys()`
# and then `shared_dict[state_name]`, so one successful foreign read costs two.
DECODES_PER_FOREIGN_READ = 2


def per_tick_cost(results):
    """Cost of one steady-state second, modelling the real access pattern.

    The read side alone understates the load badly, because
    `SharedDict.__setitem__` re-serialises the **entire dict** for **every single
    key** written. A minion that updates 7 states per tick pays 7 full encodes,
    not one.
    """
    out = {}
    for name, per_codec in results.items():
        if any(per_codec.get(m) is None for m in ("SCAN", "OMS", "SERVO", "GUI")):
            continue
        total_us_per_sec = 0.0
        detail = {}
        for minion, tick_ms in TICK_MS.items():
            timings = per_codec.get(minion) or per_codec["Cam1"]
            ticks = 1000.0 / tick_ms
            enc_us = timings[0] * WRITES_PER_TICK.get(minion, 0)
            # foreign reads decode the *peer's* dict; SCAN's is the common target
            dec_us = (
                per_codec["SCAN"][1]
                * FOREIGN_READS_PER_TICK.get(minion, 0)
                * DECODES_PER_FOREIGN_READ
            )
            us_per_sec = (enc_us + dec_us) * ticks
            detail[minion] = us_per_sec / 1e6 * 100.0
            total_us_per_sec += us_per_sec
        out[name] = (total_us_per_sec / 1e6 * 100.0, detail)
    return out


def _print_table(title, table, keys):
    print(f"\n{title}")
    width = max(len(k) for k in table) + 2
    print(" " * width + "  ".join(f"{k:>10}" for k in keys))
    for name, row in table.items():
        cells = "  ".join(f"{row[k]:>10}" for k in keys)
        print(f"{name:<{width}}{cells}")


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    print(f"codecs under test: {', '.join(CODECS)}")
    print(f"numpy {np.__version__} | python {sys.version.split()[0]}")

    problems = check_real_payloads()
    if problems:
        print(f"\nFAIL real payloads: {len(problems)} problem(s)")
        for p in problems:
            print(f"  {p}")
    else:
        print(f"\nOK   real payloads: {len(REAL_PAYLOADS)} minion dicts round trip cleanly")

    _print_table("Python type preservation", check_python_types(), list(PYTHON_TYPES))
    _print_table("numpy scalar support", check_numpy_scalars(), list(NUMPY_SCALARS))

    print(f"\nEncoded size in bytes (usable segment: {USABLE_BYTES} B)")
    sizes = check_sizes()
    names = list(CODECS)
    width = max(len(m) for m in sizes) + 2
    print(" " * width + "  ".join(f"{n:>16}" for n in names))
    for minion, row in sizes.items():
        print(f"{minion:<{width}}" + "  ".join(f"{row[n]:>16}" for n in names))

    _print_table("NaN / Infinity round trip", check_non_finite_floats(),
                 ["nan", "+inf", "-inf"])

    unsafe = check_nul_safety()
    if unsafe:
        print("\nNUL bytes present (tolerated since item 9's length prefix; was disqualifying):")
        for name, hits in unsafe.items():
            print(f"  {name}: {', '.join(hits)}")

    if "--bench" in sys.argv:
        print("\nRound-trip cost in microseconds (encode / decode)")
        results = benchmark()
        print(" " * width + "  ".join(f"{n:>18}" for n in names))
        for minion in REAL_PAYLOADS:
            cells = []
            for n in names:
                v = results[n].get(minion)
                cells.append("  n/a" if v is None else f"{v[0]:7.2f} /{v[1]:7.2f}")
            print(f"{minion:<{width}}" + "  ".join(f"{c:>18}" for c in cells))

        agg, rps = aggregate_read_cost(results)
        print(
            f"\nRead side only -- get_timestamp(): {rps:.0f} decodes of SCAN's dict "
            f"per second"
        )
        for name, (_, pct) in sorted(agg.items(), key=lambda kv: kv[1][1]):
            print(f"  {name:<18} {pct:6.2f} % of one core")

        print(
            "\nFull steady state, all 8 minions, modelling __setitem__'s per-key "
            "re-serialisation"
        )
        ptc = per_tick_cost(results)
        for name, (pct, detail) in sorted(ptc.items(), key=lambda kv: kv[1][0]):
            worst = sorted(detail.items(), key=lambda kv: -kv[1])[:3]
            share = ", ".join(f"{m} {v:.1f}%" for m, v in worst)
            print(f"  {name:<18} {pct:6.2f} % of one core   (heaviest: {share})")

        base = ptc.get("json + hook (current)")
        if base:
            print(
                f"\n  Codec-only total for the current codec: {base[0]:.2f} % of one core."
            )
            print(
                "  This is NOT the cost of the real access path. See the scope warning at"
            )
            print(
                "  the top of this file: the codec is ~2 % of a real foreign read; the NUL"
            )
            print(
                "  terminator in SharedBuffer.read is ~93 %. Fix that first."
            )
