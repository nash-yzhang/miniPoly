# Detect a crashed minion, not just a stopped one

Goal: tell "this peer shut down cleanly" apart from "this peer's process died and is
never coming back" — `is_minion_alive` alone cannot make that distinction.

## Why `is_minion_alive` is not enough

```python
alive = self.is_minion_alive('SCAN')   # True / False / None
```

`is_minion_alive` reads the peer's `status` segment and trusts the **last value it
wrote there**. That is exactly right for a graceful `shutdown()` — `_shutdown` sets
`status` to -2 on its way out, so a clean exit reads `False` immediately. It is blind to
a peer that is still technically running but stuck: a segment does not update itself
when the process behind it freezes or dies outright without running its own cleanup, so
`status` keeps reporting whatever it last was — often still `1` ("running") — forever
(see README, *Known limitations*: "A crashed minion can still look alive").

## The other signal: `heartbeat_of`

```python
h1 = self.heartbeat_of('SCAN')
# ... wait at least HEARTBEAT_INTERVAL (0.1 s) ...
h2 = self.heartbeat_of('SCAN')

if h1 is not None and h1 == h2:
    self.error('SCAN has stopped reaching the bottom of its own loop')
```

Every minion's `innerLoop` bumps its own heartbeat counter once per
`HEARTBEAT_INTERVAL` (100 ms), regardless of whether it is running, suspended, or doing
anything else — as long as `innerLoop` is still alive and cycling. `heartbeat_of` reads
that counter with no lock (it is a raw 4-byte read, deliberately outside the
lock/codec machinery `is_minion_alive` goes through). Two samples taken at least
`HEARTBEAT_INTERVAL` apart that come back **equal** mean the peer's loop is not
advancing — crashed, deadlocked, or blocked inside something that never returns —
regardless of what `status` claims.

`heartbeat_of` returns `None` in two situations that mean opposite things: the peer was
never linked, or — because a clean `_shutdown()` unlinks the heartbeat segment on its
way out — the peer already exited cleanly. Distinguish them with `is_minion_alive`:
`None` from both together means "gone, and gone on purpose."

## Putting them together

| `is_minion_alive` | heartbeat advancing? | Meaning |
|---|---|---|
| `False` (or `None` after unlink) | n/a | Clean exit |
| `True` | Yes | Genuinely running |
| `True` | No (`h1 == h2`) | **Crashed or hung** — the case `is_minion_alive` alone cannot see |

Nothing in the framework consumes this combination automatically yet — `heartbeat_of`
exists as a primitive (roadmap item 16), not a policy. A supervisor minion that wants to
notice a hung peer has to poll both itself, on whatever interval its own use case needs.
