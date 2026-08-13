"""Rig-agnostic compiler base classes.

Rig-specific implementations live in `miniPoly.contrib` and are **not exported
from here** -- getting rig-specific code must require naming `miniPoly.contrib.xxx`
explicitly, otherwise contrib's "not part of the framework contract" label is
diluted at the aggregation layer (`from miniPoly.compiler import *` would silently
hand out rig code).

Imports are lazy (PEP 562). This module previously aggregated with
`from .xxx import *`, whose side effect was that `import miniPoly.compiler`
unconditionally dragged in pyusb / pyfirmata2 / cv2 / vispy and loaded the Windows
TIS camera DLL from a class body inside tisgrabber -- so even someone who only
wanted QtCompiler needed the whole hardware dependency set. With lazy imports a
submodule is only imported when one of its names is actually requested.

The other side effect of star imports was re-exporting module-level names such as
`np`, `traceback` and `cv2`. An explicit list replaces that, so
`dir(miniPoly.compiler)` is noticeably narrower. That narrowing is intentional and
the snapshots under tests/surface/ have been updated accordingly.
"""

from importlib import import_module

#: public name -> submodule that defines it (relative to this package)
_EXPORTS = {
    # rig-agnostic base classes
    "AbstractCompiler": ".prototypes",
    "StreamingCompiler": ".prototypes",
    # graphics / GUI
    "QtCompiler": ".graphics",
    "ShaderStreamer": ".graphics",
    "resize_with_padding": ".graphics",
    # cameras
    "AbstractCameraCompiler": ".cameras",
    # optical mouse sensors
    "OMSInterface": ".serial_devices",
    "OMSDuo": ".serial_devices",
}

#: names that have left this package -> where they went (for actionable errors)
_MOVED = {
    "MotorShieldCompiler": "CaImg_App.core.motorshield in the miniPolyApp repository",
    "SerialCommandCompiler": "CaImg_App.core.motorshield in the miniPolyApp repository",
    "TISCameraCompiler": "CaImg_App.core.tiscamera in the miniPolyApp repository "
                          "(the rig-agnostic half stayed here as AbstractCameraCompiler)",
    "PololuServoInterface": "archived in miniPoly/__arc__/serial_PololuServoInterface.py",
    "ArduinoCompiler": "archived in miniPoly/__arc__/serial_ArduinoCompiler.py",
    "GLCompiler": "archived in miniPoly/__arc__/compiler_GLCompiler.py",
    "IOStreamingCompiler": "archived in miniPoly/__arc__/compiler_IOStreamingCompiler.py",
}

__all__ = sorted(_EXPORTS)


def __getattr__(name):
    """PEP 562 lazy attribute hook: import and cache the submodule that defines `name`, or raise an informative error."""
    module = _EXPORTS.get(name)
    if module is None:
        hint = ""
        if name in _MOVED:
            where = _MOVED[name]
            hint = f"; {name} has moved out of miniPoly.compiler, it is now {where}"
            if where.startswith("miniPoly"):
                hint += f" (use `from {where} import {name}`)"
        raise AttributeError(
            f"module {__name__!r} has no attribute {name!r}{hint}"
        ) from None
    value = getattr(import_module(module, __name__), name)
    globals()[name] = value  # cache so later access skips __getattr__
    return value


def __dir__():
    """Return `__all__` so lazily-imported names still show up in introspection even before they've been accessed."""
    return __all__
