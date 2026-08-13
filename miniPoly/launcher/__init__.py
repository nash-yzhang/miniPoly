"""What an application *is*, and how it starts.

Every layer below this one describes a part: `core` a process and its shared memory,
`compiler` the logic that runs inside one, `processor` the shell that pairs the two.
Nothing said what a *set* of them is.  So every application built on miniPoly wrote its
own answer -- construct, `connect`, `attach_logger`, `run`, in some order, with the
topology as Python literals -- and every one of them drifted somewhere different.

This layer is the answer, stated once:

    an application is a TOML file plus an :class:`Application` subclass.

The TOML file names the minions, what compiles each one, how they connect, in what order
they start and where the logs go.  The subclass declares the handful of things a file
cannot: which compiler keywords hold paths that ship beside it, and whatever merging that
particular application does.  Everything else is inherited.

The point is not to save the forty lines of boilerplate, though it does.  It is that two
applications built this way are legible to the same reader, and a third one cannot quietly
invent a fourth convention.

Layering: this sits *above* `processor`, which it composes and which must keep knowing
nothing about it.  :mod:`miniPoly.launcher.config` is stdlib-only and imports no miniPoly
at all, so a configuration can be parsed and validated on a machine with no PyQt5, no
vispy and no hardware drivers -- which is exactly the machine someone debugs a config on.
"""

from miniPoly.launcher.application import Application
from miniPoly.launcher.config import (
    ConfigError,
    MinionSpec,
    NULL_SENTINEL,
    RigConfig,
    apply_overrides,
    load_rig,
    resolve_class,
)

__all__ = [
    "Application",
    "ConfigError",
    "MinionSpec",
    "NULL_SENTINEL",
    "RigConfig",
    "apply_overrides",
    "load_rig",
    "resolve_class",
]
