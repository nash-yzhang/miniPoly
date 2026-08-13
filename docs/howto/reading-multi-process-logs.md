# Read logs from a multi-process rig without being misled by their order

Goal: stop treating log line order as execution order. In a rig with even two
minions, it usually is not.

## Why the order looks scrambled

Every minion logs through its own `logging.getLogger(self.name)`, wired by
`attach_logger` to send records over a `multiprocessing.Queue` to one `LoggerMinion`
process. `LoggerMinion.main` drains that queue **non-blocking**, one record per tick
(see its docstring on why: a blocking `dequeue(True)` could not observe reporter status
while waiting, which used to leave the logger parked forever once every other minion had
gone quiet). So what you see on screen is arrival order at the queue, not the order
statements executed in — and several independent OS processes are writing to it
concurrently.

Two real runs of [`examples/two_minions.py`](https://github.com/nash-yzhang/miniPoly/blob/main/examples/two_minions.py),
back to back, no code changed in between:

```
Run A:
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

Run B:
INFO LOGGER   ----------------- START LOGGING -----------------
WARNING SENSOR   Reset the callback function of the ["default"] timer
INFO SENSOR   Shared state: 'reading' created
WARNING FOLLOWER   Reset the callback function of the ["default"] timer
INFO FOLLOWER   FOLLOWER initialized
INFO SENSOR   SENSOR initialized
INFO SENSOR   SENSOR is off
INFO FOLLOWER   reading reached 50.0; taking the rig down
INFO FOLLOWER   FOLLOWER is off
INFO LOGGER   ----------------- STOP LOGGING -----------------
INFO LOGGER   LOGGER is off
```

Same script, same machine, immediately consecutive runs. Every line is present in both,
but look at where `SENSOR is off` lands.

In Run B it appears **before** `reading reached 50.0` — and read literally that is
impossible, because it is `FOLLOWER` reaching 50 that sets `SENSOR`'s status to -1 and
stops it. The cause printed after its own effect. Nothing is wrong: two processes put
their records on the queue independently, and the one that got there first is the one
you see first. Run A, three seconds earlier, happens to show the same two events the
other way round.

That is the whole lesson, and it is worth more than any amount of staring at
timestamps: **between minions, the log tells you what happened, not when.**

## What you can and cannot conclude from order

- **Can:** two lines from the *same* minion appear in the order that minion logged
  them — one process's own log calls are sequential.
- **Cannot:** line N from `SENSOR` happened before line N+1 from `FOLLOWER` just because
  it printed first. They are different processes; only shared-state reads/writes (which
  you can see in [Architecture](../architecture.md)) establish real happens-before
  relationships between them.
- **Can:** rely on a clean shutdown being complete. `LoggerMinion.shutdown` keeps draining
  until nothing has arrived for `DRAIN_GRACE`, rather than until `queue.empty()` — which
  cannot be trusted, since `put()` hands off to a feeder thread and a record can be
  logged, queued and still invisible to the reader. The stop banner is therefore always
  the last line, and a minion's final messages always precede it.
- **Cannot:** assume every line was captured when a process dies *hard*. A segfault or a
  kill takes its unflushed records with it — this is the same gap
  [Detect a crashed minion](detect-a-crashed-minion.md) exists to cover on the liveness
  side. Do not read a missing line as proof an event did not happen.

## Where the files are

`LoggerMinion` writes two, into the directory given as `log_dir` (or `[app] log_dir` in a
rig configuration file):

```
<log_dir>/20260813_154616_LOGGER.log         everything, at DEBUG
<log_dir>/ERROR_20260813_154616_LOGGER.log   the ERROR records only
```

Timestamp first so a directory listing sorts chronologically; the logger's own name after
it, because the timestamp alone is not unique — it has one-second resolution, and two
applications sharing a `log_dir` can start within the same second. Both handlers open in
`mode='w'`, so a name collision is not two writers appending, it is one truncating the
other. An application built with `[app] unique_names` carries the launching PID in its
logger's name, which makes that impossible rather than merely unlikely.

The console shows INFO and above; the file has DEBUG too, so a line missing from your
terminal is often simply below the console threshold rather than absent.

Pass `log_dir` explicitly. Its default is a `logs/` resolved against the **process working
directory**, so an unstated destination means "wherever this happened to be launched
from" — which is how 463 files totalling 1.3 GB once accumulated inside a source tree.

## Reconstructing one minion's timeline

Grep by the minion's name (the `%(name)s` field, which is `self.name` — `SENSOR`,
`FOLLOWER`, `LOGGER` above) rather than by timestamp, since names are exact and
timestamps from different processes on the same box can legitimately tie or appear
out of wall-clock order by a few milliseconds:

```
grep 'SENSOR' rig.log
```

If you need a real cross-process time base — not just "which process logged what" but
"which events on different minions happened close together" — that is what
`timer_minion` and `TIMER_TIMESTAMP` are for (see
[Timer and trigger minions](timer-and-trigger-minions.md)), not the log timestamps.
