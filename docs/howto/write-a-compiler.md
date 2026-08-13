# Write a new device compiler

Goal: wrap a piece of hardware (or any per-tick behavior) as a compiler that plugs into
a rig the same way `OMSInterface`, `AbstractCameraCompiler` and the tutorial's `Sensor`
do. Assumes you have already run through the [Tutorial](../tutorial.md).

## 1. Pick a base class

| Need | Base class |
|---|---|
| Per-tick logic only, states peers can read live | `AbstractCompiler` |
| The above, **plus** recording to CSV/binary/movie gated by a trigger minion's record switch | `StreamingCompiler` (`miniPoly.compiler.prototypes`) |

If you are not sure yet, start with `AbstractCompiler` — the tutorial's `Sensor` is one.
Move to `StreamingCompiler` only once you need a session recorded to disk; see
[State vs. streaming state](state-vs-streaming-state.md) for what that buys you.

## 2. Implement `__init__`

```python
from miniPoly.compiler.prototypes import StreamingCompiler
from miniPoly.core import contract as _contract

class MyDevice(StreamingCompiler):
    def __init__(self, *args, some_setting=None, **kwargs):
        super().__init__(*args, **kwargs)   # forwards timer_minion/trigger_minion up
        self._device = open_my_device(some_setting)
        self.create_streaming_state(_contract.DEVICE_..., 0, shared=True, use_buffer=False)
```

Two rules that come straight from `OMSInterface` (`miniPoly/compiler/serial_devices.py`),
the simplest real example in the codebase:

- Call `super().__init__(*args, **kwargs)` **first**, before touching any device or
  declaring any state — it is what registers your tick callback with the process handler
  at all (`AbstractCompiler.__init__`) and, for `StreamingCompiler`, what stores
  `timer_minion`/`trigger_minion`.
- Open the device and declare its states in the same `__init__`. States are meant to be
  declared once at startup (see `create_state`'s docstring); declaring one mid-session is
  legal but loses the startup grace period `FRAMEWORK_SEALED` gives late-linking peers.

If your device needs a fuller lifecycle — reconnect on GUI request, video-format changes,
a "wait until the user selects one" phase — read `AbstractCameraCompiler`
(`miniPoly/compiler/cameras.py`). It factors that lifecycle out into six vendor hooks
(`_open_device`, `_device_is_valid`, `_stop_device`, `_reset_device`,
`_configure_video_format`, `_capture_frame`) so a concrete camera subclass only has to
implement those six against its own SDK, not re-derive the state machine around them.

## 3. Implement `on_time`

```python
    def on_time(self, t):
        value = self._device.read()
        if value is not None:
            self.set_streaming_state(_contract.DEVICE_..., value)
        super().on_time(t)   # keeps StreamingCompiler's own streaming machinery running
```

**If you subclassed `StreamingCompiler`, always end your override with
`super().on_time(t)`.** That call is what runs `_streaming_setup`/`_streaming` every
tick; skip it and your compiler declares streaming states that never actually get
written to disk when recording is on. `AbstractCameraCompiler.on_time` follows the same
rule, just with its GUI-reaction logic ahead of the `super()` call instead of behind it.

## 4. Implement `on_close`

```python
    def on_close(self):
        self._device.release()
```

Called once, after `FRAMEWORK_STATUS` has already been set to -1 (see
`AbstractCompiler._on_close`) — so this is teardown, not a place to check `status()`
again. Anything that claims an exclusive OS resource (a USB interface, a serial port, a
file handle) belongs here; `OMSInterface.on_close`/`OMSDuo.on_close` release their USB
device for exactly this reason — leaving it out means a restart can find the device
still busy from the previous run.

## 5. Wire it into a rig

In the launcher config (see `CaImg_App/config/*.toml` for real examples):

```toml
[minion.MYDEVICE]
kind = "streaming"          # -> StreamingAPP, which validates timer_minion/trigger_minion
compiler = "mypackage.devices:MyDevice"
connect = ["SCAN", "GUI"]   # peers this minion is allowed to read from
timer_minion = "SCAN"
trigger_minion = "GUI"
refresh_interval = 5
some_setting = "whatever __init__ needs"
```

`kind` selects the process shell (`AbstractAPP`/`StreamingAPP`/`StreamingGLAPP`/
`AbstractGUIAPP`, see [Architecture](../architecture.md#class-hierarchy)); everything
else in the table becomes a keyword argument to your compiler's `__init__` via
`_param_to_compiler`. See
[Timer and trigger minions](timer-and-trigger-minions.md) for how to decide whether your
compiler needs either.
