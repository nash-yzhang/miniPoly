# Tutorial: your first rig

Two processes, no config file, no manager process, no schema. By the end you will have
run a real miniPoly rig, read its logs, and changed its behavior.

## Prerequisites

```
git clone https://github.com/nash-yzhang/miniPoly.git
cd miniPoly
uv sync --extra full
```

`uv sync` creates `.venv` and installs miniPoly itself in editable mode, so edits to the
library take effect immediately -- nothing below needs a reinstall.

## Step 1 — run it

```
uv run python examples/two_minions.py
```

You should see something close to this (exact timestamps and line order will vary --
these are three independent processes, not one script printing in sequence):

```
INFO LOGGER   ----------------- START LOGGING -----------------
WARNING SENSOR   Reset the callback function of the ["default"] timer
INFO SENSOR   Shared state: 'reading' created
WARNING FOLLOWER   Reset the callback function of the ["default"] timer
INFO FOLLOWER   FOLLOWER initialized
INFO SENSOR   SENSOR initialized
INFO FOLLOWER   reading reached 50.0; taking the rig down
INFO FOLLOWER   FOLLOWER is off
INFO SENSOR   SENSOR is off
INFO LOGGER   ----------------- STOP LOGGING -----------------
INFO LOGGER   LOGGER is off
```

The `WARNING ... Reset the callback function` lines are expected, not a problem --
every `AbstractAPP` reports it while wiring its own default timer.

`LOGGER` is started first and stops last, and that ordering is the point rather than a
detail: the other minions log *through* it, so anything it stops draining before they
have finished is lost -- and a minion's last messages are exactly the ones that say why
it stopped. Note where `LOGGER is off` sits relative to the other two.

## Step 2 — what just happened

Three OS processes started: `LOGGER`, `SENSOR`, `FOLLOWER`. `SENSOR` counted up and
published its count as a state named `reading`, 1000 times a second. `FOLLOWER` read
that state **by name**, every tick, until it crossed 50 -- then told `SENSOR` to stop and
shut itself down. `LOGGER` waited until both had gone quiet before stopping itself.

No process here was told the others' internals. `FOLLOWER` does not import `Sensor`; it
only knows the string `'reading'` and the string `'SENSOR'`. That is the whole
mechanism the rest of the framework builds on: a schema-free, name-addressed shared
state namespace, with one OS process per participant.

## Step 3 — read the code

Open [examples/two_minions.py](https://github.com/nash-yzhang/miniPoly/blob/main/examples/two_minions.py).

**The compiler classes** hold your logic. `AbstractCompiler` is the base every
device/behavior compiler subclasses (see [Architecture](architecture.md)):

```python
class Sensor(AbstractCompiler):
    def __init__(self, processHandler):
        super().__init__(processHandler)
        self.create_state('reading', 0.0)   # declared at runtime -- no schema file
        self._n = 0

    def on_time(self, t):                   # called once per tick, inside SENSOR's own process
        self._n += 1
        self.set_state('reading', self._n * 0.5)
```

`create_state` is called once, in `__init__`; `set_state` is called every tick, in
`on_time`. Nothing else in the rig had to be told `'reading'` exists — a peer that
`connect`s to `SENSOR` can read it, and one that does not, cannot.

```python
class Follower(AbstractCompiler):
    def on_time(self, t):
        if self._done:
            return
        reading = self.get_state_from('SENSOR', 'reading')
        if reading is not None and reading >= 50:
            self.set_state_to('SENSOR', 'status', -1)
            self._done = True
            self.shutdown()
```

`get_state_from(minion_name, state_name)` is the read side of the same mechanism —
by name, across a process boundary. The `is not None` check matters: `SENSOR` declares
`'reading'` inside its own process, so a fast-starting `FOLLOWER` can legitimately ask
for it before it exists yet.

The `_done` flag matters too, and for a reason worth knowing early: **`shutdown()` is a
request, not a `return`**. It marks this minion's status as stopping; the tick loop only
re-reads that status every `STATUS_POLL_INTERVAL`, so `on_time` is still called a few
more times afterwards. By then `SENSOR` is gone, and each of those extra reads would log
`Dead minion 'SENSOR'`. One flag is the whole fix — but the same shape appears in real
rigs, where the extra ticks talk to a serial port that has already been closed.

**The wiring** happens in `__main__`, in the parent process, before anything runs:

```python
sensor = AbstractAPP('SENSOR', Sensor, refresh_interval=1)      # 1 ms tick
follower = AbstractAPP('FOLLOWER', Follower, refresh_interval=1)

follower.connect(sensor)                                        # who may read whom
for minion in (sensor, follower):
    minion.attach_logger(logger)

logger.run(); sensor.run(); follower.run()
```

`AbstractAPP` is the process shell (see [Architecture](architecture.md#class-hierarchy))
that owns a compiler and gives it a real OS process to run in. Note what is passed in:
the **class** `Sensor`, not an instance. It gets constructed inside the child process —
the one structural rule the rest of the framework follows from, because it is what lets
Qt/vispy/ctypes objects live inside a minion at all under Windows `spawn`.

`connect` is directional: `follower.connect(sensor)` means `FOLLOWER` may read `SENSOR`'s
states, not the other way around. Change the argument order and `get_state_from('SENSOR',
...)` would fail — try it in Step 4.

## Step 4 — change it

Three small edits, each isolated, each runnable immediately with `uv run python
examples/two_minions.py`:

1. **Lower the threshold.** Change `reading >= 50` to `reading >= 10` in `Follower`. The
   rig should stop noticeably sooner.
2. **Add a second state.** In `Sensor.__init__`, add `self.create_state('n_ticks', 0)`,
   and in `on_time` add `self.set_state('n_ticks', self._n)`. In `Follower.on_time`, read
   it with `self.get_state_from('SENSOR', 'n_ticks')` and log it. No registry to update,
   no schema to touch — this is the "new sensor becomes a new readable value" property
   from the README.
3. **Break the wiring on purpose.** Swap the connect direction to
   `sensor.connect(follower)` instead of `follower.connect(sensor)`, and watch
   `get_state_from('SENSOR', ...)` in `FOLLOWER` come back `None` forever, because
   `FOLLOWER` was never granted a link to `SENSOR`. This is the failure mode to recognize
   later when a real rig's peer reads look stuck.

## Step 5 — stop writing the wiring

Look at what the bottom of `two_minions.py` actually says: construct, `connect`,
`attach_logger`, `run`. Those four steps are the same, in that order, for every rig ever
built on miniPoly. They carry no information about *this* rig — but they are where a new
minion is most easily forgotten, and forgetting one produces a process that starts, logs
nothing, and is never linked to its peers.

So don't write them. `miniPoly.launcher` reads the same rig from a file:

```toml
# examples/two_minions.toml
[app]
logger = "LOGGER"
run_order = ["LOGGER", "SENSOR", "FOLLOWER"]
log_dir = "logs"

[minion.SENSOR]
kind = "app"
compiler = "examples.two_minions:Sensor"
refresh_interval = 1

[minion.FOLLOWER]
kind = "app"
compiler = "examples.two_minions:Follower"
connect = ["SENSOR"]
refresh_interval = 1
```

```python
# examples/two_minions_config.py
from miniPoly.launcher import Application

class TwoMinions(Application):
    """This rig adds nothing to the framework, so there is nothing here to write."""

TwoMinions.launch("examples/two_minions.toml")
```

```
uv run python examples/two_minions_config.py
```

Identical output, because it is an identical rig. What changed is that reading one
`[minion.X]` section now tells you everything about X, and adding a third minion is four
lines in one place instead of four edits spread across a construct call, a `connect`
call, an `attach_logger` loop and a run order.

Three things in that file are worth naming, because each is a decision rather than a
formality:

- **`run_order` is required.** Start order is a real choice — entry scripts for the same
  rig have been observed to disagree about where the logger goes — so it is stated rather
  than inferred, because inferring one would silently change the other.
- **`log_dir` is required, and relative to the config file.** `LoggerMinion`'s own default
  is a `logs/` resolved against the *working directory*, so an unstated destination means
  "wherever this happened to be launched from". That is how 463 files totalling 1.3 GB
  once accumulated inside a source tree.
- **`compiler` is a string, not an import.** That is what lets the file be parsed and
  validated on a machine where the compiler's own dependencies are not installed. The cost
  is that a typo is no longer caught by your editor, which is why every path is resolved
  up front, before a single process starts.

What an application still has to declare in Python is whatever the file cannot know about
it. For this rig, nothing. For a real one, usually two things:

```python
class MyRig(Application):
    #: Compiler keywords holding a path that ships beside the config file, resolved
    #: against it. Everything else passes through exactly as written -- a data drive or
    #: a UNC share must not be rewritten, and no rule can tell those apart from a
    #: stimulus folder, so this is a list rather than a rule.
    PATH_KEYS = frozenset({"stimulus_folder", "shader_path"})

    @classmethod
    def customise(cls, spec, config_dir):
        """Whatever merging is this application's business and no other's."""
```

## Where to go next

- [Architecture](architecture.md) — how `core` → `compiler` → `processor` → `launcher` fit
  together, and where `SharedBuffer`, `TimerMinion` and the rest of what you just used
  actually live.
- The [Reference](reference/core.md) pages — every method on `AbstractCompiler`,
  `BaseMinion` and `TimerMinion` you touched above, generated from their docstrings, plus
  [launcher](reference/launcher.md) for the config format in full.
- **How-to guides** — task-oriented recipes (adding a real device compiler, debugging a
  peer read that stays `None`, adding a shared ndarray buffer for frame data) are not
  written yet; this tutorial is the on-ramp to them.
