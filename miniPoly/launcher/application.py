"""Build and launch an application from a rig configuration file.

This replaces the forty lines of boilerplate that every entry script carries verbatim:
the connect graph, one `attach_logger` call per minion, and one `run()` call per minion.
Those forty lines are identical across every application ever built on miniPoly, so they
contain no information -- but they are also where a new minion is most easily forgotten,
because forgetting one produces a process that starts, logs nothing, and is never linked
to its peers.

Every APP class has the same constructor -- ``(name, compiler, refresh_interval=...,
**kwargs)``, with kwargs forwarded untouched to the compiler -- so a `[minion.X]` table
maps onto a constructor call almost one for one.  That uniformity is what makes one
builder enough for every application: a three-minion display test and a nine-minion
closed-loop rig differ in which classes they name, not in how they are built.

Order of operations is deliberate:

1. Resolve *every* compiler class, before constructing anything.  A mistyped class path
   is the one real cost of moving a topology out of Python, and this is what pays it: the
   launch fails in under a second, names the offending key, and has not yet opened a
   serial port or moved a motor.
2. Construct all minions.  Constructors only record parameters; no process starts.
3. Wire the connect graph, then attach the logger to everything.
4. `run()` in the configured order.

Steps 1-3 start nothing, which is what makes a dry run possible: an application can be
built in full, and every parameter each process would receive inspected, on a laptop with
no hardware attached.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from miniPoly.launcher.config import (
    ConfigError,
    MinionSpec,
    RigConfig,
    apply_overrides,
    load_rig,
    resolve_class,
    validate_compilers,
)


class Application:
    """A built, not-yet-running application: subclass this to define one.

    The class attributes below are the contract.  An application declares what a config
    file cannot say about itself and inherits everything else, which is what keeps two
    applications built on this framework legible to the same reader::

        class GLApplication(Application):
            PATH_KEYS = frozenset({"renderer_path", "shader_path"})

    Kept as an object rather than a single ``launch()`` function so that a test, or a dry
    run, can build the minions and inspect their parameters without starting any process.
    """

    #: ``kind`` string -> the APP class that a `[minion.X]` table of that kind becomes.
    #:
    #: Dotted ``"module:Class"`` strings rather than the classes themselves, resolved
    #: only when a config actually names the kind.  Importing this module must not import
    #: PyQt5 or vispy: ``--help`` on a broken machine is exactly when it is most needed,
    #: and a config-file typo should not require a working GL stack to diagnose.
    #:
    #: This table lives in the library because every class in it does. Adding an APP class
    #: is one edit here, not one edit per downstream application.
    KINDS: dict[str, str] = {
        "app": "miniPoly.processor.prototypes:AbstractAPP",
        "gui": "miniPoly.processor.GUI:AbstractGUIAPP",
        "streaming": "miniPoly.processor.Streaming:StreamingAPP",
        # A StreamingAPP that owns an OpenGL context. Separate from "streaming" because
        # the class is, and because getting it wrong is not a quiet failure: a shader
        # compiler constructed as a plain StreamingAPP has no canvas to render into.
        "gl": "miniPoly.processor.Streaming:StreamingGLAPP",
        # A bare GL canvas with no stream behind it: it renders what its controller sends
        # and takes none of the stream keywords that "gl" above requires.
        "display": "miniPoly.processor.GL:GLAPP",
    }

    #: Compiler keywords whose *value is another minion's name*, used to address that peer
    #: across process boundaries.
    #:
    #: Every one of these is a miniPoly constructor keyword, so the library knows them and
    #: an application does not restate them. Two things need the set: validation, since a
    #: typo here is caught by nothing -- the connect graph is checked, but these are
    #: ordinary kwargs, so a misspelling surfaces as a minion that quietly never ticks --
    #: and `[app] unique_names`, where renaming a minion has to rename every reference to
    #: it, and a reference is only recognisable by the key it arrives under.
    REF_KEYS: frozenset[str] = frozenset({
        "display_minion",
        "controllerProcName",
        "timer_minion",
        "trigger_minion",
    })

    #: Compiler keywords naming a file or directory that ships *beside the config file*,
    #: resolved against it before being passed on.
    #:
    #: Empty here, and deliberately so: every such key is application vocabulary -- a
    #: stimulus folder, a credential file, a renderer script. The library owns the
    #: mechanism (see `resolve_path_keys`, which explains what it is defending against);
    #: an application owns the list.
    PATH_KEYS: frozenset[str] = frozenset()

    def __init__(self, config: RigConfig):
        self.config = config
        self.logger: Any = None
        self.minions: dict[str, Any] = {}
        #: Appended to every process name when `[app] unique_names` is set. Empty
        #: otherwise, so the names a config declares are the names the OS sees.
        self.suffix = ""

    # -- the hook an application overrides ---------------------------------------------

    @classmethod
    def customise(cls, spec: MinionSpec, config_dir: Path) -> None:
        """Adjust one minion's spec after parsing, before it is constructed.

        Called once per minion, with the directory the config file lives in.  Mutate
        `spec` in place; return value is ignored.

        This is where an application does whatever merging is its own business and no
        other application's -- overlaying a machine-written calibration file onto the
        parameters a human wrote, say.  Everything generic has already happened by this
        point: defaults applied, null sentinels substituted, `PATH_KEYS` resolved.

        Raise :class:`~miniPoly.launcher.config.ConfigError` to reject the config; it will
        be reported like any other structural error, before any process starts.
        """

    # -- loading -----------------------------------------------------------------------

    @classmethod
    def load(cls, path: str | Path) -> RigConfig:
        """Parse a config file under this application's declared vocabulary."""
        return load_rig(
            path,
            kinds=frozenset(cls.KINDS),
            ref_keys=cls.REF_KEYS,
            path_keys=cls.PATH_KEYS,
            customise=cls.customise,
        )

    @classmethod
    def from_file(cls, path: str | Path, overrides: list[str] | None = None) -> "Application":
        """Parse `path`, apply any ``MINION.key=value`` overrides, and return an instance."""
        config = cls.load(path)
        if overrides:
            apply_overrides(
                config, overrides, ref_keys=cls.REF_KEYS, path_keys=cls.PATH_KEYS
            )
        return cls(config)

    # -- building and running ----------------------------------------------------------

    def build(self) -> "Application":
        """Construct every minion, wire the graph, attach the logger.

        No process is started; `run` does that.
        """
        from miniPoly.processor.Logging import LoggerMinion

        compilers = validate_compilers(self.config)
        classes = {
            kind: resolve_class(dotted)
            for kind, dotted in self.KINDS.items()
            if kind in {spec.kind for spec in self.config.minions.values()}
        }

        # Runtime-unique names, if the config asked for them. Done here and not while
        # parsing because the PID is a fact about this launch, not about the file: keeping
        # the parse deterministic is what lets a test compare a parsed config against a
        # baseline, and what makes a dry run print the same thing twice.
        self.suffix = f"_{os.getpid()}" if self.config.unique_names else ""

        self.logger = LoggerMinion(
            self.config.logger_name + self.suffix, log_dir=self.config.log_dir
        )

        for name, spec in self.config.minions.items():
            app_class = classes[spec.kind]
            # `self.minions` stays keyed by the *config* name, so run_order and the
            # connect graph need no rewriting -- `connect()` takes objects. Only the name
            # a peer is addressed by across process boundaries moves.
            params = self._with_renamed_refs(spec.params)
            try:
                self.minions[name] = app_class(name + self.suffix, compilers[name], **params)
            except TypeError as exc:
                # Almost always a key in the [minion.X] table that the APP or its compiler
                # does not accept. Naming the minion and the keys it was given turns an
                # anonymous traceback into an editable line.
                raise ConfigError(
                    f"{self.config.path}: [minion.{name}] could not be constructed as "
                    f"{app_class.__name__}({name!r}, {spec.compiler}, ...): {exc}\n"
                    f"  keys given: {sorted(spec.params)}"
                ) from exc

        for name, spec in self.config.minions.items():
            for peer in spec.connect:
                self.minions[name].connect(self.minions[peer])

        for minion in self.minions.values():
            minion.attach_logger(self.logger)

        return self

    def run(self) -> None:
        """Start every process in the configured order."""
        if not self.minions:
            raise RuntimeError("build() must be called before run()")
        for name in self.config.run_order:
            if name == self.config.logger_name:
                self.logger.run()
            else:
                self.minions[name].run()

    @classmethod
    def launch(cls, path: str | Path, overrides: list[str] | None = None) -> "Application":
        """Parse, build and start the application described by `path`."""
        application = cls.from_file(path, overrides).build()
        application.run()
        return application

    # -- internals ---------------------------------------------------------------------

    def _with_renamed_refs(self, params: dict[str, Any]) -> dict[str, Any]:
        """`params` with every minion-name reference carrying the runtime suffix.

        A keyword like ``timer_minion`` or ``display_minion`` holds a *name*, which the
        receiving compiler uses to address that peer's shared segment by its OS-level
        identifier. Suffixing the minions without suffixing these would leave every one of
        them pointing at a name that no longer exists -- and because a foreign read on a
        missing peer is a wait-and-retry rather than an exception, the application would
        start clean and simply never exchange anything.

        Parsing has already checked that each of these names a declared minion, so there
        is nothing to validate here.
        """
        if not self.suffix:
            return params
        renamed = dict(params)
        for key in self.REF_KEYS & set(renamed):
            if isinstance(renamed[key], str):
                renamed[key] = renamed[key] + self.suffix
        return renamed
