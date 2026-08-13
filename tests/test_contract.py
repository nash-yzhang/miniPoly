"""Freeze the values of the shared-state key names.

Step 2b replaces scattered string literals with contract constants one by one. The
only real risk in that kind of edit is mistyping a string, which produces a silent
inter-process communication break (a read returns None instead of raising).

This test pins down each constant's value. Changing a value means changing the
protocol and must be deliberate: when editing here, confirm that the code in
miniPolyApp which provides or reads that state was changed too.

Standalone:  python tests/test_contract.py
pytest:      pytest tests/test_contract.py
"""

from miniPoly.core import contract

# constant name -> historical literal (the string the pre-refactor code used)
FROZEN = {
    "FRAMEWORK_STATUS": "status",
    "FRAMEWORK_NAME": "name",
    "FRAMEWORK_ALL": "ALL",
    # Not historical: added with roadmap item 19. Frozen here for the same reason as the
    # rest -- a mistyped key makes a peer wait the full timeout instead of failing fast,
    # with nothing raised.
    "FRAMEWORK_SEALED": "declarations_sealed",
    "COMPILER_WATCH_PREFIX": "C_",
    "BUFFER_PREFIX": "b*",
    "TIMER_TIMESTAMP": "timestamp",
    "STREAM_ENABLE": "StreamToDisk",
    "STREAM_DIR": "SaveDir",
    "STREAM_NAME": "SaveName",
    "STREAM_INIT_TIME": "InitTime",
    "PROTOCOL_RUN": "runSignal",
    "PROTOCOL_FILE": "protocolFn",
    "PROTOCOL_CMD_INDEX": "cmd_idx",
    "PROTOCOL_TIME_COLUMN": "time",
    "APP_STREAM_DEVICES": "StreamingDevices",
    "APP_FULLSCREEN": "fullscreen",
    "APP_SHADER_FILE": "FSFn",
    "APP_FBO_PREVIEW": "FBO",
    "APP_CAMERA_NAME": "CameraName",
    "APP_VIDEO_FORMAT": "VideoFormat",
    "APP_SERIAL_CMD": "serial_cmd",
    "DEVICE_OMS_X": "xPos",
    "DEVICE_OMS_Y": "yPos",
    "DEVICE_OMS_DUO_X": "sX",
    "DEVICE_OMS_DUO_Y": "sY",
    "DEVICE_OMS_DUO_R": "sR",
    "DEVICE_CAMERA_FRAME_COUNT": "FrameCount",
}

# grouped key names (tuple constants)
FROZEN_GROUPS = {
    "DEVICE_OMS_DUO_RAW": ("M1x", "M1y", "M2x", "M2y"),
}

# Derived tuples built from other constants; not registered individually.
DERIVED = {"REQUIRED_OF_TRIGGER_MINION", "REQUIRED_OF_TIMER_MINION"}


def check():
    problems = []
    for name, expected in FROZEN.items():
        actual = getattr(contract, name, None)
        if actual is None:
            problems.append(f"contract.{name} is missing (it used to be {expected!r})")
        elif actual != expected:
            problems.append(
                f"contract.{name} = {actual!r} but the protocol value must be {expected!r}"
            )

    for name, expected in FROZEN_GROUPS.items():
        actual = getattr(contract, name, None)
        if actual is None:
            problems.append(f"contract.{name} is missing (it used to be {expected!r})")
        elif tuple(actual) != expected:
            problems.append(
                f"contract.{name} = {actual!r} but the protocol value must be {expected!r}"
            )

    # Reverse direction: a new constant that was never registered here.
    registered = set(FROZEN) | set(FROZEN_GROUPS)
    defined = {
        n
        for n in dir(contract)
        if n.isupper() and isinstance(getattr(contract, n), (str, tuple))
    }
    for name in sorted(defined - registered - DERIVED):
        problems.append(f"contract.{name} is not registered in this test; add it to FROZEN")
    return problems


def test_state_names_frozen():
    problems = check()
    assert not problems, (
        "the shared-state key protocol changed:\n  " + "\n  ".join(problems)
    )


def test_required_sets_reference_real_constants():
    for group in (contract.REQUIRED_OF_TRIGGER_MINION, contract.REQUIRED_OF_TIMER_MINION):
        for value in group:
            assert value in FROZEN.values(), f"{value!r} is not a registered state key"


if __name__ == "__main__":
    import sys

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    p = check()
    if p:
        print(f"FAIL protocol values: {len(p)} problem(s)")
        for x in p:
            print(f"  {x}")
        raise SystemExit(1)
    total = len(FROZEN) + sum(len(v) for v in FROZEN_GROUPS.values())
    print(f"OK   protocol values: {total} key names match their historical literals")
    test_required_sets_reference_real_constants()
    print("OK   required-state tuples reference only registered constants")
