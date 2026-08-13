# Decide whether a minion needs a timer_minion / trigger_minion

Goal: figure out, for a compiler you are writing or configuring, whether it needs
`timer_minion`, `trigger_minion`, both, or neither.

## They are roles, not types

> No fixed roles. `timer_minion` (the clock) and `trigger_minion` (the control
> source) are constructor arguments, not types. Any minion can be either, and a rig
> with neither is legal.
> — README, *What you get*

There is no `TimerMinionRole` class to inherit from. In the rig's real config
(`CaImg_App/config/VR_P136NW.toml`), `SCAN` — an ordinary `kind = "streaming"` serial
compiler that happens to parse an Arduino stream — is `timer_minion` for every other
minion, and `GUI` — an ordinary `kind = "gui"` minion — is `trigger_minion` for
everything:

```toml
[defaults.streaming]
timer_minion = "SCAN"
trigger_minion = "GUI"
```

Nothing about `SCAN` or `GUI`'s class makes them eligible for these roles beyond the
states they happen to publish.

## Do you need `timer_minion` at all?

Only if you subclass `StreamingCompiler` and call `get_timestamp()` — used to
timestamp every streamed CSV row and to compute `running_time` during a protocol.
`timer_minion` must name a minion that publishes `contract.TIMER_TIMESTAMP`
(milliseconds; `contract.REQUIRED_OF_TIMER_MINION` documents this).

If you leave it `None`, `get_timestamp()` does not fail — it falls back to
`time.perf_counter()`, which is monotonic but **local to this process only**, not
comparable to any other minion's timestamps. That is fine for a standalone tool (the
tutorial's plain `AbstractCompiler`s never call `get_timestamp` at all) and wrong for
anything whose recorded rows need to line up against another minion's rows on the same
time axis — which is every device in a real rig, hence one shared `timer_minion` for
all of them above.

## Do you need `trigger_minion` at all?

Only if you subclass `StreamingCompiler`. It is not optional there:
`StreamingAPP.__init__` validates both `timer_minion` and `trigger_minion` are given and
logs an error (aborting construction) if either is `None`. `trigger_minion` must name a minion
publishing the three states in `contract.REQUIRED_OF_TRIGGER_MINION`:
`STREAM_ENABLE`, `STREAM_DIR`, `STREAM_NAME` — the record on/off switch and where to
write. `AbstractCameraCompiler` additionally reads `APP_STREAM_DEVICES` from the same
minion, to decide *which* cameras are actually selected in the GUI (its `should_stream`
override) — a `StreamingCompiler` does not have to read anything beyond the three
required states, but nothing stops a subclass from reading more from the same trigger
minion, the way this one does.

A plain `AbstractCompiler` (not `StreamingCompiler`) never needs a `trigger_minion` —
there is no streaming lifecycle to gate. The tutorial's `Sensor`/`Follower` are exactly
this case.

## Quick decision

| Your compiler is... | needs `timer_minion`? | needs `trigger_minion`? |
|---|---|---|
| Plain `AbstractCompiler`, no recording | No | No |
| `StreamingCompiler` subclass | Yes, if you want cross-minion-comparable timestamps in the recorded CSV (almost always, in a real rig) | Yes, always — the process shell validates it |
| The minion *providing* `TIMER_TIMESTAMP` (e.g. `SCAN`) | No — it does not read its own clock through `get_timestamp` | Depends on whether it itself streams |
| The minion *providing* the record switch (e.g. `GUI`) | Depends on whether it itself streams | No — it is not reading a trigger minion, it *is* one |
