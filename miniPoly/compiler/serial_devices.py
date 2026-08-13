"""Optical mouse sensor (OMS) compilers.

This module also used to hold PololuServoInterface and ArduinoCompiler (now
archived) plus SerialCommandCompiler and MotorShieldCompiler (now moved to
miniPoly/contrib/motorshield.py). The module name is deliberately kept as
serial_devices so that the downstream import
`from miniPoly.compiler.serial_devices import OMSDuo, OMSInterface` keeps working.
"""

import traceback

import numpy as np
import usb.core
import usb.util

from miniPoly.compiler.prototypes import StreamingCompiler
# Underscore alias keeps `contract` out of this module's public namespace.
from miniPoly.core import contract as _contract


class OMSInterface(StreamingCompiler):
    """Compiler for a single USB optical mouse sensor (OMS) reporting relative X/Y motion.

    Reads raw reports from a device selected by USB vendor/product ID and
    publishes a moving-average-smoothed (x, y) position as streaming state.
    """

    def __init__(self, *args, VID=None, PID=None, timeout=1, mw_size=1, **kwargs):
        """Open the USB device by VID/PID and declare its streaming X/Y states.

        Raises `ValueError` if VID/PID are not given or no matching device is
        found -- there is no retry loop here (unlike the camera compilers), the
        device is expected to already be connected when this runs.
        """
        super(OMSInterface, self).__init__(*args, **kwargs)
        if VID is None or PID is None:
            raise ValueError('VID and PID must be set')
        else:
            self._VID = VID
            self._PID = PID

        self.device = usb.core.find(idVendor=self._VID, idProduct=self._PID)
        if self.device is not None:
            self.device.set_configuration()
            self._endpoint = self.device[0][(0,0)][0]
        else:
            raise ValueError(f'Device not found. VID: {self._VID}, PID: {self._PID}')

        self._timeout = timeout
        self._mw_size = mw_size
        self._pos_buffer = np.zeros((self._mw_size, 2))

        self.create_streaming_state(_contract.DEVICE_OMS_X,0, shared=True, use_buffer=False)
        self.create_streaming_state(_contract.DEVICE_OMS_Y,0, shared=True, use_buffer=False)
        # self.create_state(_contract.DEVICE_OMS_X, 0)
        # self.create_state(_contract.DEVICE_OMS_Y, 0)

    def on_time(self, t):
        """Read the device and publish a moving-average of its (x, y) position as streaming state."""
        try:
            x, y = self._read_device()
            if x is not None and y is not None:
                self._pos_buffer = np.roll(self._pos_buffer, -1, axis=0)
                self._pos_buffer[-1, 0] = x
                self._pos_buffer[-1, 1] = y
                xPos,yPos = np.nanmean(self._pos_buffer, axis=0)

                self.set_streaming_state(_contract.DEVICE_OMS_X, xPos)
                self.set_streaming_state(_contract.DEVICE_OMS_Y, yPos)
        except:
            print(traceback.format_exc())

        super().on_time(t)

    def _read_device(self):
        """Read one raw report from the device and decode it into normalized (x, y) deltas.

        Bytes 2 and 4 of the report hold the raw x/y motion, decoded to a
        [-1, 1)-ish range around zero; returns (None, None) on a read timeout.
        """
        try:
            data = self.device.read(self._endpoint.bEndpointAddress, self._endpoint.wMaxPacketSize, self._timeout)
            if data is not None:
                x = data[2]
                y = data[4]
                if x > 127:
                    x = (x - 256)/128
                else:
                    x = (x+1)/128
                if y > 127:
                    y = (y - 256)/128
                else:
                    y = (y+1)/128
                return x, y
        except:
            self.debug('OMS device timeout')
            return None, None

    def on_close(self):
        """Release the USB device claimed by `__init__`.

        `set_configuration()` claims the interface for this process and nothing gave it
        back: the handle only died with the process, so a restart could find the device
        still busy. `_on_close` has already set FRAMEWORK_STATUS to -1 by the time this
        runs, which is why the write that used to live here is gone rather than moved.
        Failure is logged, never raised -- teardown must not be able to kill the minion.
        """
        try:
            usb.util.dispose_resources(self.device)
        except Exception:
            self.debug(f'Failed to release OMS device:\n{traceback.format_exc()}')



class OMSDuo(StreamingCompiler):
    """Compiler for two synchronized USB optical mouse sensors, combined into 2D translation plus rotation.

    Mirrors `OMSInterface` for a device pair (e.g. two sensors under a
    spherical treadmill): each sensor's raw X/Y is decoded independently, then
    combined into forward/lateral speed (`sX`/`sY`) and heading change (`sR`).
    """

    def __init__(self, *args, VID=[], PID=[], device_coordinates=[], device_scale_fac = [1, 1], timeout=1, mw_size=1, **kwargs):
        """Open both USB devices by VID/PID, then declare the combined and per-device streaming states.

        Raises `ValueError` if VID/PID/device_coordinates are not each length-2,
        or if either device is not found.
        """
        super(OMSDuo, self).__init__(*args, **kwargs)
        if any([len(VID) != 2,len(PID)!= 2,len(device_coordinates)!= 2]):
            raise ValueError('VID, PID and device_coordinate must have the same length')
        else:
            self._VID = VID
            self._PID = PID
            self._device_scale_fac = device_scale_fac
            self.raw_vec = np.array([0,0,0,0])
            self.sX = 0
            self.sY = 0
            self.sR = 0

        self.device = [usb.core.find(idVendor=self._VID[0], idProduct=self._PID[0]),
                       usb.core.find(idVendor=self._VID[1], idProduct=self._PID[1])]
        if any(self.device):
            self.device[0].set_configuration()
            self.device[1].set_configuration()
            self._endpoint = [self.device[0][0][(0,0)][0],self.device[1][0][(0,0)][0]]
        else:
            raise ValueError(f'Device not found. VID: {self._VID}, PID: {self._PID}')

        self._timeout = timeout
        self._mw_size = mw_size
        self._pos_buffer = np.zeros((self._mw_size, 4))

        self._init_states()

    def _init_states(self):
        """Declare the streaming states for combined rotation/X/Y and each device's raw values."""
        self.create_streaming_state(_contract.DEVICE_OMS_DUO_R,0, shared=True, use_buffer=False)
        self.create_streaming_state(_contract.DEVICE_OMS_DUO_X,0, shared=True, use_buffer=False)
        self.create_streaming_state(_contract.DEVICE_OMS_DUO_Y,0, shared=True, use_buffer=False)
        for _raw_name in _contract.DEVICE_OMS_DUO_RAW:
            self.create_streaming_state(_raw_name, 0, shared=True, use_buffer=False)

    def on_time(self, t):
        """Read both devices and, if either produced new data, publish the combined motion states."""
        try:
            should_update = self._read_device()
            if should_update:
                self._update_states()
        except:
            print(traceback.format_exc())

        super().on_time(t)

    def _update_states(self):
        """Publish the combined sR/sX/sY and each device's raw values as streaming state."""
        self.set_streaming_state(_contract.DEVICE_OMS_DUO_R, self.sR)
        self.set_streaming_state(_contract.DEVICE_OMS_DUO_X, self.sX)
        self.set_streaming_state(_contract.DEVICE_OMS_DUO_Y, self.sY)
        for _i, _raw_name in enumerate(_contract.DEVICE_OMS_DUO_RAW):
            self.set_streaming_state(_raw_name, self.raw_vec[_i])

    def _read_device(self):
        """Read one report from each USB sensor, decode their deltas, and combine them into forward/lateral/rotational motion.

        Adapted from the ADNS3080 Arduino controller referenced below: each
        sensor's raw byte pair is sign-decoded via its "sign" byte, smoothed
        with a moving average, then combined assuming the two sensors are
        mounted at right angles on a treadmill ball. Returns False (leaving
        state untouched) when neither sensor reported motion, or on error.
        """
        self._pos_buffer = np.roll(self._pos_buffer, -1, axis=0)
        self._pos_buffer[-1,:] = [0,0,0,0]
        should_update = np.array([0, 0])
        try:
            dev0_data = self.device[0].read(self._endpoint[0].bEndpointAddress, self._endpoint[0].wMaxPacketSize, self._timeout)
            if dev0_data is not None:
                x0 = dev0_data[2]
                xs = dev0_data[3]
                y0 = dev0_data[4]
                ys = dev0_data[5]
                if xs < 127:
                    x0 = x0/255
                else:
                    x0 = (x0-255)/255
                if ys < 127:
                    y0 = -y0/255
                else:
                    y0 = (255-y0)/255

                self._pos_buffer[-1, 0] = x0
                self._pos_buffer[-1, 1] = y0
                should_update[0] = 1
            else:
                self._pos_buffer[-1, :2] = 0#self._pos_buffer[-2, :2]

            dev1_data = self.device[1].read(self._endpoint[1].bEndpointAddress, self._endpoint[1].wMaxPacketSize, self._timeout)
            if dev1_data is not None:
                x1 = dev1_data[2]
                xs = dev1_data[3]
                y1 = dev1_data[4]
                ys = dev1_data[5]
                if xs < 127:
                    x1 = x1/255
                else:
                    x1 = (x1-255)/255
                if ys < 127:
                    y1 = -y1/255
                else:
                    y1 =  (255-y1)/255

                self._pos_buffer[-1, 2] = x1
                self._pos_buffer[-1, 3] = y1
                should_update[1] = 1
            else:
                self._pos_buffer[-1, 2:] = 0

            if np.sum(should_update)>0 or np.sum(self._pos_buffer) != 0:
                xPos0, yPos0 = np.nanmean(self._pos_buffer[:, :2], axis=0)
                xPos1, yPos1 = np.nanmean(self._pos_buffer[:, 2:], axis=0)
                self.raw_vec = [xPos0, yPos0, xPos1, yPos1]

                # Adapted from https://github.com/sn-lab/MouseGoggles/blob/main/Other%20Hardware/Spherical%20Treadmill/ADNS3080_Mouse_Controller_V5/ADNS3080_Mouse_Controller_V5.ino
                self.sX = yPos0 * self._device_scale_fac[0]
                self.sY = yPos1 * self._device_scale_fac[1]
                self.sR = (xPos0 * self._device_scale_fac[1] + xPos1 * self._device_scale_fac[1])*0.5
                return True
            else:
                return False
        except Exception as e:
            if 'timeout' not in str(e):
                self.debug(traceback.format_exc())
            # else:
                # self.debug('OMS device timeout')
            return False


    def on_close(self):
        """Release both USB devices claimed by `__init__`.

        Same contract as `OMSInterface.on_close`, over the pair: each is disposed
        independently so a failure on the first still frees the second, and neither can
        raise out of teardown. `_on_close` has already set FRAMEWORK_STATUS to -1, which
        is why the write that used to live here is gone rather than moved.
        """
        for i, device in enumerate(self.device):
            try:
                usb.util.dispose_resources(device)
            except Exception:
                self.debug(f'Failed to release OMS device {i}:\n{traceback.format_exc()}')
