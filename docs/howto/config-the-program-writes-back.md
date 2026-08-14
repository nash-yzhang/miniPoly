# Config the program writes back

Some of a rig's configuration is not something a human types. A motor's travel limits, a
camera's measured offset, a mirror's zero position: the operator drives the hardware to a
reference point, presses a button, and the value that lands in the config is a
**measurement**. Next launch has to read it back.

This is a different kind of value from a COM port, and it needs a different file.

## Why not just write it into the TOML

Two reasons, and the second is the one that bites.

`tomllib` is read-only — the standard library has no TOML writer, so the process would need
a third-party dependency just to save a number.

And a machine-rewritten config file loses its comments. The hand-written half of a rig
config is where the COM ports, the network paths and the "why is this 20 and not 1" notes
live; those are exactly the lines a serialiser drops. Round-tripping the file every time an
operator presses **Save** would delete the documentation that makes the file readable.

So the split is: **one TOML that a human writes, one JSON that the program writes.**
`[app.writeback]` is how you connect them.

## Declare it

```toml
# rig.toml -- the half a human writes
[app.writeback]
key        = "calibration"
target     = "motor_dict"
path_param = "motor_config"
payload    = "motors"
fields     = ["min_pos", "max_pos", "offset"]

[minion.SERVO]
kind = "streaming"
compiler = "my_rig.core.motors:MotorCompiler"
calibration = "calib_rig1.json"      # <- `key`, resolved against this file

[minion.SERVO.motor_dict]            # <- `target`
light_pin = 7

[minion.SERVO.motor_dict.axis_x]
ID = 1                               # configuration: stays here
step_distance = 0.05                 # configuration: stays here
```

```json
// calib_rig1.json -- the half the program writes
{
  "rig": "rig1, west bench",
  "note": "recalibrated after the mount was replaced",
  "saved": "2026-08-14T14:18:07",
  "motors": {
    "axis_x": { "min_pos": 118, "max_pos": 3894, "offset": 11.6 }
  }
}
```

The five names, and why each is separate:

| key | what it names |
|---|---|
| `key` | the `[minion.X]` keyword a minion opts in with. Its value is the JSON file, relative to the config file, so a config directory can be moved as a unit |
| `target` | the parameter the loaded entries are overlaid onto, per named entry |
| `path_param` | the parameter the `Writeback` handle is injected as, for the compiler to save through (see [launcher reference](../reference/launcher.md)) |
| `payload` | the top-level key inside the JSON holding the entries |
| `fields` | the only per-entry fields the file may carry |

Only minions that name `key` are affected. Every other `[minion.X]` in the same file is
untouched, so one rig can have a calibrated servo and an uncalibrated camera.

## Read it

Nothing to do — it has already happened. By the time your compiler is constructed,
`motor_dict["axis_x"]` holds `ID`, `step_distance` **and** the three measured fields, merged.
The TOML's own value for a field the JSON also has is overwritten; a field only the TOML has
survives.

## Write it

The parameter named by `path_param` arrives as a `Writeback` handle. Call `save`:

```python
class MotorCompiler(StreamingCompiler):
    def __init__(self, processHandler, motor_dict=None, motor_config=None, **kwargs):
        super().__init__(processHandler, **kwargs)
        self._motor_config = motor_config   # a Writeback, or None if this rig has no file

    def save_calibration(self):
        if self._motor_config is None:
            self.error("no write-back file configured; add a 'calibration' key")
            return
        measured = {
            name: {
                "min_pos": self.hardware.minimum(name),
                "max_pos": self.hardware.maximum(name),
                "offset": self.hardware.offset(name),
            }
            for name in self.axes
        }
        self._motor_config.save(measured)
        self.info(f"saved calibration to {self._motor_config}")
```

The handle carries the payload key and the field whitelist as well as the path, so your
compiler states only the values it measured and nothing about the file's shape. `str()` on it
is the path, which is what you want in a log line.

It is a frozen dataclass of a `Path` and two names, which is deliberate: on Windows a minion
is *spawned* rather than forked, so every parameter is pickled on its way into the process. A
bound method or a closure would not survive that.

## What it refuses, and why

**A field not in `fields`.** On both read and write. A typo'd key that is quietly dropped is
indistinguishable from a good save — the operator sees the button work and finds out at the
next session. Keep `fields` to the values that are genuinely measurements: `ID`,
`step_distance` and `resolution` above are configuration, and letting them into the JSON
would split one setting across two files, each able to win.

**An entry that is not in `target`.** A write-back file naming `axis_q` when the config
declares only `axis_x` is an error, not an addition. The tempting alternative would let a
stale file resurrect an axis that was deliberately removed from the setup, and the failure
would surface as the compiler addressing hardware that is not on the bus — far from its
cause.

**A file that cannot be read.** Parsing stops the launch rather than falling back to the
TOML's own values, because the alternative is a rig that runs on the wrong geometry without
saying so.

## What it guarantees

**The file that was read is the file that is written.** `path_param` is derived from `key`,
not declared separately, so the two cannot drift apart.

**The save is atomic.** It writes a `.tmp` beside the target and `os.replace`s it. This file
is the only record of a calibration session; a crash or power cut partway through a plain
write would leave a truncated file and no values, and they cannot be recovered by re-reading
any code.

**Your comments survive.** Every top-level key other than `payload` is read back and carried
over, so `rig` and `note` above outlive any number of machine rewrites. Only `payload` and
`saved` are replaced — `saved` is stamped for you.

## Before 1.1

This was one application's 163-line module, plus an `Application` subclass and a `customise`
hook to call it. Only five names in it were ever that rig's; the rest was the mechanism above.
The names moved into the config file, the mechanism moved here beside the reader it is the
counterpart of, and the subclass and the hook were deleted — see
[the launcher reference](../reference/launcher.md).
