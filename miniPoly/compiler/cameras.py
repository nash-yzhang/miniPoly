"""Rig-agnostic camera compiler: state/buffer/streaming lifecycle for a device
that exposes one video frame at a time.

Vendor SDKs are not part of the framework contract (see miniPoly.contrib), so
this class holds no vendor calls. A
subclass provides them through six hooks, all of which touch the concrete
device object it is responsible for creating in `_open_device`:

    _open_device(device_name)      connect to and open the named device
    _device_is_valid() -> bool     is the device currently open and usable
    _stop_device()                 stop the live video stream
    _reset_device()                replace the device handle with a fresh one
    _configure_video_format(fmt)   apply a video format
    _capture_frame() -> ndarray    grab the current frame

The Imaging Source implementation that used to live here moved to
CaImg_App/core/tiscamera.py, alongside the `tisgrabber` bindings it depends on
-- see that module's docstring for the split rationale.
"""

import traceback
from time import sleep

from miniPoly.compiler.prototypes import StreamingCompiler
# Underscore alias keeps `contract` out of this module's public namespace.
from miniPoly.core import contract as _contract


class AbstractCameraCompiler(StreamingCompiler):
    """Base compiler for a device that produces one video frame per tick.

    Owns the state/buffer/streaming plumbing shared by every camera; a concrete
    subclass supplies the six vendor hooks documented in the module docstring
    (`_open_device`, `_device_is_valid`, `_stop_device`, `_reset_device`,
    `_configure_video_format`, `_capture_frame`).
    """

    #: Name of the trigger-minion state used to decide which devices stream.
    #: This is a pure GUI concept (which cameras the user ticked) and therefore a
    #: library -> application boundary leak. Exposing it as a class attribute lets
    #: subclasses point at a different state without overriding should_stream().
    STREAM_DEVICE_FILTER_STATE = _contract.APP_STREAM_DEVICES

    #: Seconds between polls while waiting for the user to pick a camera in the GUI.
    DEVICE_WAIT_INTERVAL = 0.01

    def __init__(self, *args, camera_name=None, save_option='binary', **kwargs):
        """Declare the camera's shared state and streaming buffer, then block until the GUI selects a device.

        `camera_name` is accepted for API symmetry but is not used directly here --
        the device actually opened is whatever `APP_CAMERA_NAME` holds once
        `_init_camera` sees it set.
        """
        super(AbstractCameraCompiler, self).__init__(*args, **kwargs)

        self.frame_rate = 1000 / self.refresh_interval
        self._camera_name = camera_name
        self._buffer_name = None
        self._buf_img = None
        self.frame_shape = None
        # Keys map one-to-one onto shared state names, so use contract constants.
        self._params = {_contract.APP_CAMERA_NAME: None, _contract.APP_VIDEO_FORMAT: None,
                        _contract.STREAM_DIR: None, _contract.STREAM_NAME: None,
                        _contract.STREAM_ENABLE: False, _contract.STREAM_INIT_TIME: 0.,
                        _contract.DEVICE_CAMERA_FRAME_COUNT: int(0)}
        self.streaming = False
        self._BIN_FileHandle = None
        self._stream_init_time = None
        self._n_frame_streamed = None
        self.camera = None

        if save_option in ['binary', 'movie']:
            self.save_option = save_option
        else:
            raise ValueError("save_option must be either 'binary' or 'movie'")

        for k, v in self._params.items():
            if k == _contract.DEVICE_CAMERA_FRAME_COUNT:
                self.create_streaming_state(k, v, shared=False)
            else:
                self.create_state(k, v)
        self._init_camera()
        self.info(f"Camera {self.name} initialized.")

    def _is_shutting_down(self):
        """True once this minion's status has gone non-positive.

        `status()` reaches the status segment through `SharedNdarray.read()`, which
        returns None when it cannot take the lock, so the comparison has to tolerate
        None. Treating None as "keep waiting" matches the original `== -1` test, which
        could not raise.
        """
        status = self.status()
        return status is not None and status <= 0

    def _init_camera(self):
        """Poll shared state until the GUI publishes a camera name and video format, then open and configure the device.

        Runs once per camera selection (also called again from `on_time` when the
        user picks a different camera). Blocks the compiler's tick loop until
        either both values are set or the minion starts shutting down.
        """
        self.info("Searching camera...")

        # Two changes from the original `== -1` with no sleep (B6):
        #  * `<= 0` -- shutdown drives the status to -1 and then _shutdown() sets -2, so
        #    a minion that reached -2 while this loop was spinning would never see -1
        #    again and the loop never exited.
        #  * a sleep -- this loop runs while the user picks a camera in the GUI, so it
        #    used to burn one core per camera compiler, and VR_init.py starts three.
        for param in (_contract.APP_CAMERA_NAME, _contract.APP_VIDEO_FORMAT):
            while self._params[param] is None:
                self._params[param] = self.get_state(param)
                if self._is_shutting_down():
                    return None
                sleep(self.DEVICE_WAIT_INTERVAL)

        device_name = self._params[_contract.APP_CAMERA_NAME]
        self.info(f"Camera {device_name} found")
        self._open_device(device_name)
        self.watch_state(_contract.APP_CAMERA_NAME, device_name)
        self._camera_name = device_name.replace(' ', '_')
        self.update_video_format()
        self.info(f"Camera {device_name} initialized")

    def update_video_format(self):
        """Stop the device if running, apply the configured video format, and (re)create the frame buffer for it.

        The buffer name is derived from the video format string because different
        formats can have different frame shapes; switching formats therefore needs
        a new buffer rather than a resize of the old one.
        """
        if self._device_is_valid():
            self._stop_device()
        video_format = self._params[_contract.APP_VIDEO_FORMAT]
        self._configure_video_format(video_format)
        buffer_name = f"frame_{video_format}".replace(' ', '_')
        frame = self._capture_frame()

        # NOTE Two independent buffers with the same name, plus a write to each, is the
        # workaround from commit c478595 ("dirty workaround by creating a local buffer for
        # streaming + a shared buffer for preview"). It changed the *call pattern* to route
        # around A1 without fixing it. A1 is now fixed in set_streaming_buffer(), so a
        # single `create_streaming_buffer(..., shared=True)` and a single
        # set_streaming_buffer() would do the same job with one shared-memory segment and
        # one write per frame fewer -- at 200 Hz across three cameras.
        #
        # Kept as it is on purpose: it is redundant, not wrong, and collapsing it cannot be
        # verified without a vendor camera attached. Collapse it on the rig, and check the
        # remove_streaming_buffer path (see docs/PROJECT_OVERVIEW.md 4-C14) when you do,
        # since buffer_name would then also live in _shared_buffers.
        self.frame_shape = frame.shape
        if self.has_state(buffer_name):
            self.set_state(buffer_name, frame)
            self.set_streaming_buffer(buffer_name, frame)
        else:
            self.create_shared_buffer(buffer_name, frame)  # create a buffer for sharing only
            self.create_streaming_buffer(buffer_name, frame, saving_opt=self.save_option, shared=False) # create a buffer for streaming to local disk only
        self._buffer_name = buffer_name


    def on_time(self, t):
        """React to GUI changes to the selected camera or video format, otherwise capture the next frame.

        Overrides `AbstractCompiler.on_time`: after handling its camera-specific
        work it still calls `super().on_time(t)`, so the inherited streaming
        setup/teardown (`StreamingCompiler.on_time`) keeps running every tick.
        """
        try:
            cameraName = self.get_state(_contract.APP_CAMERA_NAME)
            if self.watch_state(_contract.APP_CAMERA_NAME, cameraName):
                if cameraName is not None:
                    self._init_camera()
                else:
                    try:
                        self.disconnect_camera()
                        self.info("Camera disconnected")
                    except:
                        self.error("An error occurred while disconnecting the camera")
                        self.debug(traceback.format_exc())
            else:
                self._params[_contract.APP_VIDEO_FORMAT] = self.get_state(_contract.APP_VIDEO_FORMAT)
                if self.watch_state(_contract.APP_VIDEO_FORMAT, self._params[_contract.APP_VIDEO_FORMAT]):
                    self.update_video_format()
                if self._device_is_valid():
                    self.process_frame()
        except:
            self.error("An error occurred while updating the camera")
            self.error(traceback.format_exc())

        super().on_time(t)

    def process_frame(self):
        """Capture a frame, publish it to the preview and streaming buffers, and advance the streamed-frame counter."""
        self._streaming_setup()
        frame = self._capture_frame()
        self.set_state(self._buffer_name, frame)
        self.set_streaming_buffer(self._buffer_name, frame)
        if self.streaming:
            self.set_streaming_state(_contract.DEVICE_CAMERA_FRAME_COUNT, self.get_streaming_state(_contract.DEVICE_CAMERA_FRAME_COUNT) + 1)
        else:
            self.set_streaming_state(_contract.DEVICE_CAMERA_FRAME_COUNT, 0)

    def should_stream(self):
        """Override of `StreamingCompiler.should_stream`: stream only if this camera is in the GUI's selected-device list."""
        device_list = self.get_state_from(self._trigger_minion, self.STREAM_DEVICE_FILTER_STATE)
        if device_list is None:
            return False
        else:
            if self._params[_contract.APP_CAMERA_NAME] in device_list:
                return True
            else:
                return False

    def disconnect_camera(self):
        """Stop and reset the device, then clear the cached device parameters."""
        self._stop_device()
        self._reset_device()
        # NOTE This key set differs from the _params built in __init__ (SaveDir /
        # SaveName / StreamToDisk / InitTime are dropped, Trigger / FrameTime are
        # added). That is a pre-existing defect, see docs/PROJECT_OVERVIEW.md 4-C14.
        # Only the literals are consolidated here; behaviour is unchanged.
        self._params = {_contract.APP_CAMERA_NAME: None, _contract.APP_VIDEO_FORMAT: None,
                        'Trigger': 0, _contract.DEVICE_CAMERA_FRAME_COUNT: 0, 'FrameTime': 0}

    def on_close(self):
        """Override of `AbstractCompiler.on_close`: disconnect the camera if it is still open when the minion shuts down."""
        if self.camera is not None:
            if self._device_is_valid():
                self.disconnect_camera()
                self.camera = None

    # ------------------------------------------------------------------
    # Vendor hooks. A subclass implements all six against its own SDK.
    # ------------------------------------------------------------------

    def _open_device(self, device_name):
        """Connect to and open the device named `device_name`.

        Vendor hook -- a subclass must override this; the base implementation only
        raises `NotImplementedError`.
        """
        raise NotImplementedError

    def _device_is_valid(self):
        """Return whether the device is currently open and usable.

        Vendor hook -- a subclass must override this; the base implementation only
        raises `NotImplementedError`.
        """
        raise NotImplementedError

    def _stop_device(self):
        """Stop the live video stream.

        Vendor hook -- a subclass must override this; the base implementation only
        raises `NotImplementedError`.
        """
        raise NotImplementedError

    def _reset_device(self):
        """Replace the device handle with a fresh one.

        Vendor hook -- a subclass must override this; the base implementation only
        raises `NotImplementedError`.
        """
        raise NotImplementedError

    def _configure_video_format(self, video_format):
        """Apply `video_format` to the device.

        Vendor hook -- a subclass must override this; the base implementation only
        raises `NotImplementedError`.
        """
        raise NotImplementedError

    def _capture_frame(self):
        """Grab and return the current frame as an ndarray.

        Vendor hook -- a subclass must override this; the base implementation only
        raises `NotImplementedError`.
        """
        raise NotImplementedError
