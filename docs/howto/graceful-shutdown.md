# Shut down a multi-minion rig cleanly

Goal: stop every process in a rig without leaving one hung, without losing its last
log lines, and without the mistake that looks like it should work from the parent
script but does not.

## The mistake: calling `.shutdown()` from the parent script

```python
sensor = AbstractAPP('SENSOR', Sensor, refresh_interval=1)
sensor.run()
...
sensor.shutdown()   # looks reasonable. Raises KeyError: 'b*SENSOR_status'.
```

`shutdown()` just sets `self.status = -1`, and the `status` property reads/writes
`self._shared_buffer[self._status_name]` — a dict entry populated by
`prepare_shared_buffer()`, which only runs **inside the child process**, from
`innerLoop`, after `run()` spawns it. `run()` hands your `sensor` object to
`multiprocessing.Process` by pickling it; the child gets its own copy and populates
*that* copy's `_shared_buffer`. The `sensor` variable still sitting in your `__main__`
scope is the original, pre-spawn object — its `_shared_buffer` is still the empty `{}`
from `__init__`, forever. There is no way to shut a minion down from a plain reference
held in the process that spawned it.

## The pattern that actually works: shut it down from a peer

This is what `examples/two_minions.py`'s `Follower` does, and it is the only correct
shape — request the stop **from inside another process that is linked to it**:

```python
class Follower(AbstractCompiler):
    def on_time(self, t):
        reading = self.get_state_from('SENSOR', 'reading')
        if reading is not None and reading >= 50:
            self.set_state_to('SENSOR', 'status', -1)   # ask SENSOR to stop...
            self.shutdown()                               # ...then stop itself
```

`set_state_to(minion_name, ...)` only works if `minion_name` is in `self._linked_minion`
— i.e. this minion called `connect(sensor)` on it beforehand. Writing `'status'`
through the shared-memory link reaches the *live* copy running inside `SENSOR`'s own
process, which is what a plain attribute write from a stale parent-side object cannot
do.

`self.shutdown()` (no minion name) is the one case that always works, because it always
runs from inside the minion's own process, against its own live `_shared_buffer` — call
it on `self` from within a compiler's own `on_time`/`on_close`, never on an `AbstractAPP`
object held by the code that called `run()` on it.

## What happens after `status` goes to -1

Nothing immediate. `shutdown()` only requests the stop; `innerLoop` notices on its next
`STATUS_POLL_INTERVAL` poll (5 ms, not every iteration — see the constant's docstring
for why that bound exists) and only then breaks its tick loop into `_shutdown()`, which,
in order: flushes any state writes still pending from the last tick, sets `status` to
-2 (dead — distinct from -1, "asked to stop"; peers must poll for `<= 0`, not `== -1`),
disconnects every remaining link, and unlinks its heartbeat segment last. A peer's
`heartbeat_of` reading `FileNotFoundError` after that point is the reliable "this
minion exited cleanly" signal — see
[Detect a crashed minion](detect-a-crashed-minion.md).

## Why the logger has to start first and stop last

`attach_logger` must be called on every minion **before** `run()` — its docstring is
explicit that this is a hard requirement, not a convention, since the actual
`logging.config.dictConfig` call happens later inside `innerLoop`, but messages logged
during a minion's own startup are lost if the queue wiring was not already in place.
`attach_logger` also calls `logger.register_reporter(self)`, which is what enrolls a
minion in `LoggerMinion.poll_reporter`'s "has everyone gone quiet" check.

You never call `logger.shutdown()` yourself in the normal case. `LoggerMinion.main`
calls `poll_reporter()` every tick and shuts itself down once every registered reporter
reads dead — so the logger's own lifetime is derived from its reporters', not managed
independently. The practical checklist:

1. Construct every `AbstractAPP`/`StreamingAPP` and the `LoggerMinion`, in the parent
   process — nothing has started yet.
2. Wire `connect()` for whichever minions need to read each other, and `attach_logger`
   on every one of them.
3. `run()` everything. Starting the logger first is the convention every example and
   config in this repo follows, so early messages spend the least possible time
   sitting in the queue unread — but it is not the hard requirement `attach_logger`'s
   ordering is.
4. To stop the rig, call `shutdown()` from inside whichever minion(s) should trigger
   the stop, cascading to linked peers via `set_state_to(peer, 'status', -1)` as shown
   above. Do not call it on parent-held references.
5. The logger notices every reporter has gone quiet and stops itself last — nothing
   else to do.
