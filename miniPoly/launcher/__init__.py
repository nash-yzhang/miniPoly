"""What an application *is*, and how it starts.

Every layer below this one describes a part: `core` a process and its shared memory,
`compiler` the logic that runs inside one, `processor` the shell that pairs the two.
Nothing said what a *set* of them is.  So every application built on miniPoly wrote its
own answer -- construct, `connect`, `attach_logger`, `run`, in some order, with the
topology as Python literals -- and every one of them drifted somewhere different.

This layer is the answer, stated once:

    an application is a TOML file.

The file names the minions, what compiles each one, how they connect, in what order they
start, where the logs go, which of its keywords hold a path beside it, and which of its
values the running program writes back.  Nothing else is needed, and in particular no
Python: :class:`Application` is a builder every application shares rather than a base class
each one extends.

It said "a TOML file plus an :class:`Application` subclass" until 2026-08-14.  There were
two subclasses, one per application, and between them they declared two lists of names and a
merge whose only implementation was one of those lists.  Lists of names are data, so they
moved into the file; the merge became ``[app.writeback]``.  Both subclasses then had nothing
in them, which is the answer to whether the "plus" was ever carrying weight.

The point is not to save the forty lines of boilerplate, though it does.  It is that two
applications built this way are legible to the same reader, and a third one cannot quietly
invent a fourth convention.

Layering: this sits *above* `processor`, which it composes and which must keep knowing
nothing about it.  :mod:`miniPoly.launcher.config` is stdlib-only and imports no miniPoly
at all, so a configuration can be parsed and validated on a machine with no PyQt5, no
vispy and no hardware drivers -- which is exactly the machine someone debugs a config on.
:mod:`miniPoly.launcher.run` is the three steps between a command line and a running
application, and imports no CLI library for the same kind of reason.
"""

from miniPoly.launcher.application import Application
from miniPoly.launcher.config import (
    ConfigError,
    MinionSpec,
    NULL_SENTINEL,
    RigConfig,
    Writeback,
    WritebackDecl,
    apply_overrides,
    load_rig,
    resolve_class,
)
from miniPoly.launcher.run import (
    DRY_RUN_HELP,
    SET_HELP,
    launch_config,
    report,
    resolve_config,
)

__all__ = [
    "Application",
    "ConfigError",
    "DRY_RUN_HELP",
    "MinionSpec",
    "NULL_SENTINEL",
    "RigConfig",
    "SET_HELP",
    "Writeback",
    "WritebackDecl",
    "apply_overrides",
    "launch_config",
    "load_rig",
    "report",
    "resolve_class",
    "resolve_config",
]
