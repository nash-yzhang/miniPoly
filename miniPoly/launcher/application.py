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
    RigConfig,
    apply_overrides,
    load_rig,
    resolve_class,
    validate_compilers,
)


class Application:
    """A built, not-yet-running application.

    Not subclassed.  Both class attributes below are tables of *framework* classes and
    *framework* keywords, so they are the same for every application; everything that
    varies between applications is in its config file.  Until 2026-08-14 there was a
    subclass per application, each declaring one or two lists of names -- which keywords
    hold a neighbouring file's path, and what the running program writes back.  Both lists
    moved into the config, since a list of names is data, and both subclasses then had
    nothing left in them.

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

    def __init__(self, config: RigConfig):
        self.config = config
        self.logger: Any = None
        self.minions: dict[str, Any] = {}
        #: Appended to every process name when `[app] unique_names` is set. Empty
        #: otherwise, so the names a config declares are the names the OS sees.
        self.suffix = ""

    # -- loading -----------------------------------------------------------------------

    @classmethod
    def load(cls, path: str | Path) -> RigConfig:
        """Parse a config file, validating it against the framework's own vocabulary.

        There used to be a `customise` hook here, called once per minion so an application
        could overlay a machine-written file onto the parameters a human wrote.  Its only
        implementation was that overlay, so the overlay became `[app.writeback]` and
        :func:`~miniPoly.launcher.config.load_rig` does it directly.  An application needing
        a merge of some other shape overrides this method.
        """
        return load_rig(path, kinds=frozenset(cls.KINDS), ref_keys=cls.REF_KEYS)

    @classmethod
    def from_file(cls, path: str | Path, overrides: list[str] | None = None) -> "Application":
        """Parse `path`, apply any ``MINION.key=value`` overrides, and return an instance."""
        config = cls.load(path)
        if overrides:
            # `config.path_keys` rather than a class attribute: the file declared them, and
            # a `--set` value has to be resolved against the same set the file's own values
            # were, or the two halves of one keyword would follow different rules.
            apply_overrides(
                config, overrides, ref_keys=cls.REF_KEYS, path_keys=config.path_keys
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
