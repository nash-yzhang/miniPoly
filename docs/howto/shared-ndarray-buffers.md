# Share frame data through a SharedNdarray buffer, not a state

Goal: publish something too big for the regular state namespace — a camera frame, a
rendered preview, any array — without going through `SharedDict`.

## Why not just `create_state`

> The state namespace is for state, not for bulk data. One 8 KB JSON segment per
> minion, rewritten as a whole on flush.
> — README, *Known limitations*

`SharedDict` decodes and re-encodes its whole segment on every read/write. A camera
frame in there would mean JSON-encoding an array on every tick, at whatever the camera's
tick rate is. `SharedNdarray` is the other primitive `core/buffer.py` provides for
exactly this case: a fixed-shape array in raw shared memory, read and written with no
encode/decode step, guarded by its own lock.

## The three ways to get one

All three ultimately create a `SharedNdarray`; they differ in whether the result is
addressable through the normal state API and whether it also gets written to disk.

**1. A plain shared buffer**, readable via `get_state` like any other state:

```python
self.create_shared_buffer('preview_frame', frame)   # frame: np.ndarray
```

This is `create_state(name, val, use_buffer=True)`'s underlying call
(`BaseMinion.create_shared_buffer`). It records an indirection entry in the SharedDict
(`name -> 'b*{minion}_{name}'`) so a peer's ordinary `get_state('preview_frame')`
transparently follows it into the buffer — the peer does not need to know it is not a
regular JSON-backed state.

**2. A streaming buffer**, written to a binary or movie file once per tick while
recording is on (only on a `StreamingCompiler` subclass):

```python
self.create_streaming_buffer('frame', frame, saving_opt='movie', shared=True)
...
self.set_streaming_buffer('frame', frame)   # every tick, in on_time
```

`saving_opt` picks the on-disk format: `'binary'` (raw bytes, via `open(..., 'wb')`) or
`'movie'` (`cv2.VideoWriter`, one frame per changed row — see
`StreamingCompiler._streaming`). `shared=True` also does step 1's work, so the same
buffer is both live-readable by peers and recorded.

**3. Both, as two separate buffers** — the pattern `AbstractCameraCompiler` actually
uses today (`compiler/cameras.py`, `update_video_format`):

```python
self.create_shared_buffer(buffer_name, frame)                                    # preview only
self.create_streaming_buffer(buffer_name, frame, saving_opt=self.save_option,
                             shared=False)                                        # disk only
```

This is a known redundancy (two shared-memory segments and two writes per frame where
one would do), kept as-is because collapsing it requires a real camera to verify against
— see the `NOTE` above `update_video_format` in that file. **Prefer option 2** (a single
`shared=True` streaming buffer) in new code; reach for option 3's split only if you have
a concrete reason peers should see a different buffer than the one being recorded.

## Reading a foreign buffer

Whichever way it was created, a peer attaches to a shared buffer the same way it reads
any other foreign state — `get_state_from(minion_name, buffer_name)` — since the
indirection in step 1 makes it transparent, and no extra locking is your
responsibility: `SharedNdarray.read()` already acquires and releases the read lock
around the copy it returns, on every call. You only need to manage a `SharedNdarray`'s
lifetime yourself (typically with a `with` block, to guarantee `close()` runs) if you
instantiate one directly instead of going through `create_shared_buffer`/
`get_state_from` — not part of the normal compiler-authoring path this guide covers.
