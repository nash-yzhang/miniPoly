# Choose: shared state, streaming state, or a plain attribute

Goal: decide which of `AbstractCompiler`'s and `StreamingCompiler`'s several ways of
holding a value is the right one for a particular piece of data. Three independent
questions, not one:

1. **Does another minion need to read it live, across a process boundary?**
2. **Does it need to end up in the session's recorded CSV** (only possible on a
   `StreamingCompiler`)?
3. **Is it big** (an image, a long buffer) rather than a scalar/short value?

## Decision table

| Cross-process? | Recorded? | Big? | Use |
|---|---|---|---|
| No | No | — | A plain Python attribute (`self._n` in the tutorial's `Sensor`). Nothing here needs the framework at all. |
| Yes | No | No | `create_state(name, val)` / `set_state` / `get_state_from` |
| Yes | No | Yes | `create_state(name, val, use_buffer=True)` — see [Shared ndarray buffers](shared-ndarray-buffers.md) |
| No | Yes | No | `create_streaming_state(name, val, shared=False)` |
| Yes | Yes | No | `create_streaming_state(name, val, shared=True)` |
| — | Yes | Yes | `create_streaming_buffer(name, val, saving_opt=..., shared=True/False)` — see [Shared ndarray buffers](shared-ndarray-buffers.md) |

`create_streaming_state`/`create_streaming_buffer` only exist on `StreamingCompiler`
subclasses. A plain `AbstractCompiler` (like the tutorial's `Sensor`/`Follower`) only
ever needs the first three rows.

## Why these are separate mechanisms

`create_state` is the tutorial's mechanism: declare a name once, `set_state`/`get_state`
it every tick, any linked peer can read it whenever it wants. There is no concept of a
"session" here — it is just always current.

`create_streaming_state` adds a second, independent thing: a row in a CSV file, written
once per tick **while `self.streaming` is True**, and only when the value actually
changed since the last row (`StreamingCompiler._streaming`, which diffs against
`_last_row` — so a flat signal produces a sparse file, not one row per tick). Whether
that CSV gets written at all is gated by the trigger minion's `STREAM_ENABLE` state
(see [Timer and trigger minions](timer-and-trigger-minions.md)), not by anything the
compiler decides on its own.

`shared=True` on `create_streaming_state` just means "also register this as a normal
shared state" — it calls `create_state` under the hood. That is why the table above has
both a "shared, not recorded" row and a "shared and recorded" row: visibility to peers
and presence in the recorded file are orthogonal, and `shared` is the only knob that
couples them.

## Reading and writing them back

Once declared, always go through the streaming accessors on a `StreamingCompiler`
subclass — `get_streaming_state`/`set_streaming_state`, not `get_state`/`set_state`
directly — even for a `shared=True` state:

```python
self.set_streaming_state(_contract.DEVICE_OMS_X, x_pos)   # right: keeps the CSV row in sync
self.set_state(_contract.DEVICE_OMS_X, x_pos)              # wrong on a StreamingCompiler: the
                                                             # streaming registry's cached copy
                                                             # goes stale, so the CSV keeps
                                                             # writing the old value
```

`get_streaming_state` re-reads shared memory on every call for a `shared=True` state
(so a peer's write is seen immediately) but returns the local cache for a `shared=False`
one — you never need to think about which case you are in; call the streaming accessor
either way.
