"""Single definition point for every shared-state key name.

All inter-process semantics in miniPoly are encoded in `SharedDict` key names.
Before this module those names existed only as string literals scattered across
two repositories -- nothing declared which states a conforming trigger minion
must provide, so nobody could implement one without reading the whole source.
The long-standing coexistence of `fullscreen` and `fullScreen` was a direct
consequence of having no single definition point.

Names are grouped by ownership, and **the grouping is itself a boundary
declaration**:

    FRAMEWORK_* / TIMER_*  framework-reserved, maintained by BaseMinion or the
                           designated timer minion
    STREAM_*               defined and read by StreamingCompiler
    PROTOCOL_*             grey area: semantics owned by the library, values
                           supplied by the trigger minion
    APP_*                  [BOUNDARY LEAK] the library reading a state that an
                           application is expected to provide by convention

Every use site of an `APP_*` constant is one library -> application coupling
still to be cleaned up. **New code should not add APP_* constants**; shortening
the APP_* list is the progress metric for the boundary work.

Usage::

    from miniPoly.core import contract
    is_streaming = self.get_state_from(self._trigger_minion, contract.STREAM_ENABLE)
"""

# -- Framework-reserved: created and maintained by BaseMinion ----------------
FRAMEWORK_STATUS = 'status'
"""int. Minion lifecycle: 1=running  0=suspended  -1=shutdown requested  -2=down.

Stored in a dedicated SharedNdarray buffer rather than the SharedDict, under a
'b*'-prefixed name. Note the difference between -1 and -2: code polling for
shutdown must test `<= 0`, not `== -1`.
"""

FRAMEWORK_NAME = 'name'
"""str. The minion's own name; `link_minion()` uses it to verify that the peer it
connected to is the intended one."""

FRAMEWORK_ALL = 'ALL'
"""Pseudo key. `get_state('ALL')` / `get_state_from(m, 'ALL')` returns the whole
state dictionary."""

FRAMEWORK_SEALED = 'declarations_sealed'
"""bool. False from the moment the segment exists; set True by `innerLoop` once
`initialize()` has returned, i.e. once the compiler's `__init__` -- the only place
that declares the initial state namespace -- is complete.

Exists because `link_minion` succeeding proves only that the segment exists, not
that the states inside it do (defect B11). A peer waiting for a state can now tell
"not declared yet" from "not going to be declared", and `get_foreign_state` stops
waiting on the second. A one-way latch: `create_state` after sealing is still legal
(camera frame buffers are named from a runtime video format), it just no longer
comes with a grace period."""

COMPILER_WATCH_PREFIX = 'C_'
"""Prefix that `AbstractMinionMixin.watch_state()` adds to compiler-side watch
keys, keeping them distinct from minion-side watch keys."""

BUFFER_PREFIX = 'b*'
"""When a SharedDict value starts with this prefix, the value is the name of a
SharedNdarray and reads are transparently redirected to that buffer.
See SharedDict._BUFFER_PREFIX."""


# -- Time base: supplied by the minion designated as timer_minion -------------
TIMER_TIMESTAMP = 'timestamp'
"""Numeric, in **milliseconds**. Every compiler's `get_timestamp()` reads this and
divides by 1000 to get seconds.

In CaImg_App it is written by `ScanListener` after parsing the Arduino serial
stream. Note that it currently lives in the JSON-encoded SharedDict, which makes
it a hot path on the global lock at a 1 ms refresh interval
(see docs/PROJECT_OVERVIEW.md section 2.2).
"""


# -- Streaming control: supplied by the minion designated as trigger_minion ---
STREAM_ENABLE = 'StreamToDisk'
"""bool. A rising edge triggers `_prepare_streaming()` + `_start_streaming()`;
a falling edge triggers `_stop_streaming()`."""

STREAM_DIR = 'SaveDir'
"""str. Must be an existing directory, otherwise streaming refuses to start."""

STREAM_NAME = 'SaveName'
"""str. File name stem, without extension."""

STREAM_INIT_TIME = 'InitTime'
"""Streaming start timestamp. Currently only used by IOStreamingCompiler
(archived)."""


# -- Protocol execution: semantics from the library, values from the trigger ---
PROTOCOL_RUN = 'runSignal'
"""bool. Protocol run switch. The compiler writes it back to False when a
protocol finishes on its own."""

PROTOCOL_FILE = 'protocolFn'
"""str. Path to an .xlsx protocol file. Empty string or None means not loaded."""

PROTOCOL_CMD_INDEX = 'cmd_idx'
"""int. Row of the protocol currently being executed; -1 means not running."""

PROTOCOL_TIME_COLUMN = 'time'
"""Name of the time column inside the protocol table. This is a DataFrame column
name, not a shared state."""


# -- Boundary leaks: the library reading application conventions ---------------
# The existence of these constants is itself design debt. The trailing comment on
# each one points at the read site inside the library.
APP_STREAM_DEVICES = 'StreamingDevices'
"""list[str]. Which devices the user ticked for streaming in the GUI.

Read site: AbstractCameraCompiler.should_stream() (miniPoly.compiler.cameras).
This is a pure GUI concept that leaked into the library -- the library has no
business knowing which cameras a user selected.
"""

APP_FULLSCREEN = 'fullscreen'
"""bool. Whether the stimulus window is fullscreen.
Read site: ShaderStreamer.set_fullscreen().

Historically a second spelling `fullScreen` (capital S) also existed, inside the
now-archived GLCompiler. This constant is the single spelling going forward.
"""

APP_SHADER_FILE = 'FSFn'
"""str. Fragment shader file path. Read site: ShaderStreamer.get_FS()."""

APP_FBO_PREVIEW = 'FBO'
"""SharedNdarray. Rendered frame handed back to the GUI for preview.

Read site: ShaderStreamer.on_draw(). Note the buffer is shaped (W,H,3) while
`_fbo.read()` produces (H,W,3); the application currently compensates with a
transpose (see docs/PROJECT_OVERVIEW.md section 4-A2).
"""

APP_CAMERA_NAME = 'CameraName'
"""str. Camera unique name. Read site: AbstractCameraCompiler._init_camera()
(miniPoly.compiler.cameras), vendor-specific subclasses in miniPolyApp."""

APP_VIDEO_FORMAT = 'VideoFormat'
"""str. Camera video format. Read site: AbstractCameraCompiler.update_video_format()
(miniPoly.compiler.cameras), vendor-specific subclasses in miniPolyApp."""

APP_SERIAL_CMD = 'serial_cmd'
"""str. Debug aid: a raw serial command to send verbatim.
Read site: MotorShieldCompiler.on_time() (CaImg_App.core.motorshield in the
miniPolyApp repository -- not part of miniPoly)."""


# -- Device-specific states ---------------------------------------------------
# These names ought to be private to their compilers, but they are in fact read
# across processes by name, which makes them part of the contract:
#   - the GUI subscribes to them via surveillance_state
#     (CaImg_App/app_setter/VR_init.py:29)
#   - streamed CSV column names are built from them, and downstream analysis
#     scripts depend on those columns
# Renaming one breaks the readability of already-recorded data.
DEVICE_OMS_X = 'xPos'
"""OMSInterface: single-sensor x displacement."""

DEVICE_OMS_Y = 'yPos'
"""OMSInterface: single-sensor y displacement."""

DEVICE_OMS_DUO_X = 'sX'
"""OMSDuo: fused spherical x displacement."""

DEVICE_OMS_DUO_Y = 'sY'
"""OMSDuo: fused spherical y displacement."""

DEVICE_OMS_DUO_R = 'sR'
"""OMSDuo: fused spherical rotation."""

DEVICE_OMS_DUO_RAW = ('M1x', 'M1y', 'M2x', 'M2y')
"""OMSDuo: raw readings of both sensors, ordered
(sensor1 x, sensor1 y, sensor2 x, sensor2 y).

Given as a tuple rather than four constants because they are always created and
written as a group (see OMSDuo._init_states / _update_states).
"""

DEVICE_CAMERA_FRAME_COUNT = 'FrameCount'
"""AbstractCameraCompiler subclasses: frames captured in the current streaming
session; 0 when not streaming."""


#: States a trigger minion must provide -- usable for a startup self-check.
REQUIRED_OF_TRIGGER_MINION = (
    STREAM_ENABLE,
    STREAM_DIR,
    STREAM_NAME,
)

#: States a timer minion must provide.
REQUIRED_OF_TIMER_MINION = (TIMER_TIMESTAMP,)
