"""Parse a rig configuration file: one TOML document describes one application.

Before this format, an application was an entry script: a Python file that mixed four
things with different owners and different rates of change -- the topology (which minions
exist and what compiles them), the wiring (COM ports, IP addresses, directories), any
calibration, and the run-time parameters (refresh intervals, save options).  A rig with
seven such scripts had seven copies that had drifted apart, with no way to tell whether a
difference was deliberate or merely stale.

The split this module draws is between *what a human writes* and *what the program writes
back*.  Everything a human writes lives in one TOML file, one section per minion, so
reading a minion's section tells you everything about it.  Anything the running program
edits belongs in a separate file of its own, because `tomllib` cannot write and because a
machine-rewritten file loses the comments that COM ports and network paths most need.

This module is deliberately stdlib-only.  It imports no miniPoly, so a configuration can
be parsed and validated on a machine with no framework and no hardware installed; turning
a parsed config into live minions is :mod:`miniPoly.launcher.application`.

The three sets that vary between applications -- which kinds exist, which keywords name a
peer minion, which keywords name a neighbouring file -- are parameters here rather than
constants, and :class:`~miniPoly.launcher.application.Application` is where an application
declares them.
"""

from __future__ import annotations

import tomllib
from collections.abc import Callable
from dataclasses import dataclass, field
from importlib import import_module
from pathlib import Path
from typing import Any

#: TOML has no null literal, but a compiler keyword can legitimately take None -- a
#: protocol column with no device behind it, a shader that is not loaded at startup.  In
#: an entry script that meaning was carried by a bare `None` and was entirely implicit.
#: Spelling it makes the intent visible in the file itself.
NULL_SENTINEL = "@none"

#: Keys of a `[minion.X]` table that configure the builder rather than the compiler.
#: Everything else in the table is passed through to the APP constructor as a keyword.
RESERVED_KEYS = frozenset({"kind", "compiler", "connect"})


class ConfigError(Exception):
    """A rig configuration file is malformed, inconsistent, or self-contradictory."""


@dataclass
class MinionSpec:
    """One minion, fully resolved: defaults applied and any application merge done."""

    name: str
    kind: str
    #: Import path of the compiler class, ``"package.module:ClassName"``.
    compiler: str
    #: Names of peers to `connect()` to.  `BaseMinion.connect` is symmetric and
    #: idempotent (it recurses into the peer and checks for an existing queue first),
    #: so declaring a link on one side, both sides, or twice all behave identically.
    connect: list[str] = field(default_factory=list)
    #: Keyword arguments for the APP constructor, which passes them to the compiler.
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class RigConfig:
    """A parsed rig file, ready for :mod:`miniPoly.launcher.application` to build."""

    path: Path
    minions: dict[str, MinionSpec]
    logger_name: str
    #: Order in which to call `run()`.  Explicit rather than derived: entry scripts for
    #: the same rig have been observed to disagree about it -- one ran the logger last,
    #: another first -- so there is no safe order to infer and guessing one would change
    #: behaviour on migration.
    run_order: list[str]
    #: Absolute directory for the logger's two output files.  Required, for the same
    #: reason `run_order` is: `LoggerMinion`'s default writes to a *relative* ``logs/``,
    #: so the destination was never a decision -- it was wherever the application
    #: happened to be launched from.  That accident once put 1.3 GB of debug logs inside
    #: a source tree.  There is no safe default to infer, because any relative path
    #: reproduces the bug.
    log_dir: Path
    #: Suffix every process name with the launching process's PID at build time.
    #:
    #: A minion's heartbeat is an OS-level *named* shared memory segment, so two
    #: applications built from the same file collide on every name. That is a real
    #: requirement for an application meant to be run twice at once -- a manual session
    #: and an automated one. It stays opt-in because the opposite is also real: an
    #: application that must not be started twice is better served by the second launch
    #: failing on a name collision than by two of them fighting over one serial port.
    unique_names: bool = False

    def compiler_paths(self) -> dict[str, str]:
        return {name: spec.compiler for name, spec in self.minions.items()}


def _substitute_nulls(value: Any) -> Any:
    """Recursively replace the null sentinel with a real ``None``."""
    if isinstance(value, str):
        return None if value == NULL_SENTINEL else value
    if isinstance(value, dict):
        return {k: _substitute_nulls(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute_nulls(v) for v in value]
    return value


def load_rig(
    path: str | Path,
    *,
    kinds: frozenset[str] | set[str],
    ref_keys: frozenset[str] = frozenset(),
    path_keys: frozenset[str] = frozenset(),
    customise: Callable[[MinionSpec, Path], None] | None = None,
) -> RigConfig:
    """Parse a rig TOML file into a :class:`RigConfig`.

    Every structural error is raised here, before any minion is constructed and therefore
    before any serial port is opened or any motor moves.

    `kinds`, `ref_keys` and `path_keys` come from the
    :class:`~miniPoly.launcher.application.Application` subclass being launched; see there
    for what each means.  `customise` is that class's per-minion hook, called once per
    minion with its spec and the directory the config file lives in, after everything
    generic has been resolved.
    """
    path = Path(path)
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"rig config not found: {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path} is not valid TOML: {exc}") from exc

    app_table = raw.get("app", {})
    if not isinstance(app_table, dict):
        raise ConfigError(f"{path}: [app] must be a table")

    minion_tables = raw.get("minion", {})
    if not isinstance(minion_tables, dict) or not minion_tables:
        raise ConfigError(f"{path}: at least one [minion.<NAME>] table is required")

    defaults = raw.get("defaults", {})
    if not isinstance(defaults, dict):
        raise ConfigError(f"{path}: [defaults] must be a table of per-kind tables")
    for kind in defaults:
        if kind not in kinds:
            raise ConfigError(
                f"{path}: [defaults.{kind}] is not a valid kind; "
                f"expected one of {sorted(kinds)}"
            )

    minions: dict[str, MinionSpec] = {}
    for name, table in minion_tables.items():
        minions[name] = _build_spec(name, table, defaults, path, kinds, path_keys, customise)

    # Every connect target must exist.  Left unchecked, a typo produces an
    # AttributeError deep inside the builder naming the wrong object.
    for spec in minions.values():
        for peer in spec.connect:
            if peer not in minions:
                raise ConfigError(
                    f"{path}: [minion.{spec.name}] connects to '{peer}', which is not "
                    f"declared (have {sorted(minions)})"
                )
            if peer == spec.name:
                raise ConfigError(f"{path}: [minion.{spec.name}] connects to itself")

    validate_minion_refs(minions, ref_keys, str(path))

    logger_name = app_table.get("logger", "LOGGER")
    if not isinstance(logger_name, str):
        raise ConfigError(f"{path}: [app] logger must be a string")
    if logger_name in minions:
        raise ConfigError(
            f"{path}: logger name '{logger_name}' collides with [minion.{logger_name}]"
        )

    run_order = app_table.get("run_order")
    if run_order is None:
        raise ConfigError(
            f"{path}: [app] run_order is required. Entry scripts for the same rig have "
            "disagreed about start order, so it cannot be inferred safely."
        )
    if not isinstance(run_order, list) or not all(isinstance(n, str) for n in run_order):
        raise ConfigError(f"{path}: [app] run_order must be a list of minion names")

    # The logger is listed in run_order like any other process, because its position is a
    # real choice that entry scripts have made differently. Inferring one would silently
    # change the other.
    runnable = set(minions) | {logger_name}
    missing = sorted(runnable - set(run_order))
    if missing:
        raise ConfigError(f"{path}: [app] run_order omits {missing}")
    unknown = sorted(set(run_order) - runnable)
    if unknown:
        raise ConfigError(f"{path}: [app] run_order names undeclared process(es) {unknown}")
    if len(set(run_order)) != len(run_order):
        raise ConfigError(f"{path}: [app] run_order lists a minion more than once")

    log_dir = app_table.get("log_dir")
    if log_dir is None:
        raise ConfigError(
            f"{path}: [app] log_dir is required. LoggerMinion's default writes to a "
            "relative 'logs/', so an unstated destination means the process working "
            "directory -- which is how 1.3 GB of debug logs once ended up inside a package."
        )
    if not isinstance(log_dir, str):
        raise ConfigError(f"{path}: [app] log_dir must be a path string")
    # Relative to the rig file, like everything else a rig file names, so a config
    # directory can be moved as a unit. An absolute path is left as written.
    log_path = Path(log_dir)
    if not log_path.is_absolute():
        log_path = path.parent / log_path

    unique_names = app_table.get("unique_names", False)
    if not isinstance(unique_names, bool):
        raise ConfigError(f"{path}: [app] unique_names must be true or false")

    return RigConfig(
        path=path,
        minions=minions,
        logger_name=logger_name,
        run_order=run_order,
        log_dir=log_path.resolve(),
        unique_names=unique_names,
    )


def _build_spec(
    name: str,
    table: Any,
    defaults: dict[str, Any],
    path: Path,
    kinds: frozenset[str] | set[str],
    path_keys: frozenset[str],
    customise: Callable[[MinionSpec, Path], None] | None,
) -> MinionSpec:
    where = f"{path}: [minion.{name}]"
    if not isinstance(table, dict):
        raise ConfigError(f"{where} must be a table")

    kind = table.get("kind")
    if kind not in kinds:
        raise ConfigError(f"{where} has kind={kind!r}; expected one of {sorted(kinds)}")

    compiler = table.get("compiler")
    if not isinstance(compiler, str) or ":" not in compiler:
        raise ConfigError(
            f"{where} needs compiler = \"package.module:ClassName\", got {compiler!r}"
        )

    connect = table.get("connect", [])
    if not isinstance(connect, list) or not all(isinstance(c, str) for c in connect):
        raise ConfigError(f"{where}: connect must be a list of minion names")

    # Per-kind defaults, so that timer_minion/trigger_minion -- which every streaming
    # minion needs and no GUI takes -- can be stated once without reaching the GUI.
    params: dict[str, Any] = dict(defaults.get(kind, {}))
    for key, value in table.items():
        if key not in RESERVED_KEYS:
            params[key] = value
    params = _substitute_nulls(params)

    resolve_path_keys(params, path_keys, path.parent, where)

    spec = MinionSpec(
        name=name,
        kind=kind,
        compiler=compiler,
        connect=list(connect),
        params=params,
    )
    if customise is not None:
        customise(spec, path.parent)
    return spec


def resolve_path_keys(
    params: dict[str, Any], path_keys: frozenset[str], base: Path, where: str
) -> None:
    """Resolve every `path_keys` entry in `params` against `base`, in place.

    Every key an application puts in this set was a bug before it was a rule.  The shape
    is always the same: a compiler keyword written as a bare or ``../``-prefixed path, and
    resolved by the compiler against the **process working directory** -- so it worked only
    because the application happened to be launched from one particular folder, and moving
    the launcher took a minion down at startup.

    Existence is checked here rather than left to the compiler, which is the point of the
    whole exercise: a compiler that raises on a missing file does so in its own process,
    possibly the eighth to start, so a stale path took the rig down after seven processes
    had come up and a camera had opened.  Failing here costs a second and names the file.

    `base` is the config file's directory when the value came from the file, and the
    working directory when it came from ``--set``: a path typed at a shell means what it
    means at that shell, and one written in a config file means what it means beside that
    file.  Both are anchors that were chosen; neither is the accident this prevents.

    An application declares this set explicitly rather than inheriting a rule, because
    every obvious rule is wrong.  Matching a `_dir`/`_folder` suffix would also catch a
    data drive, a remote host and a UNC share, which must pass through exactly as written.
    Adding a key is a deliberate act, which is the point.
    """
    for key in sorted(path_keys & set(params)):
        value = params[key]
        # A path key with a null value is a real setting, not an omission: a shader that
        # is not loaded at startup, a database that this rig does not write to.
        # `_substitute_nulls` has already turned the sentinel into None, so the key is
        # present with nothing to resolve.
        if value is None:
            continue
        if not isinstance(value, str):
            raise ConfigError(f"{where}: {key} must be a path string, got {value!r}")
        resolved = Path(value)
        if not resolved.is_absolute():
            resolved = base / resolved
        resolved = resolved.resolve()
        if not resolved.exists():
            raise ConfigError(
                f"{where}: {key} = {value!r} resolves to {resolved}, which does not exist. "
                f"Paths in {', '.join(sorted(path_keys))} are relative to {base}."
            )
        # Passed on as a string: these reach compilers that hand them to Qt's file dialog,
        # to os.path.exists and to open(). A Path works by accident today and would not
        # after any of them is concatenated.
        params[key] = str(resolved)


def validate_minion_refs(
    minions: dict[str, MinionSpec], ref_keys: frozenset[str], where: str
) -> None:
    """Every `ref_keys` value must name a declared minion.

    These are ordinary compiler keywords rather than graph edges, so the connect check
    does not see them: an unvalidated ``timer_minion = "SCNA"`` produces a minion that
    links to a peer which never exists, waits out the framework's retry on every tick, and
    reports nothing wrong.
    """
    for spec in minions.values():
        for key in sorted(ref_keys & set(spec.params)):
            peer = spec.params[key]
            if peer is None:
                continue
            if not isinstance(peer, str):
                raise ConfigError(
                    f"{where}: [minion.{spec.name}] {key} must be a minion name, got {peer!r}"
                )
            if peer not in minions:
                raise ConfigError(
                    f"{where}: [minion.{spec.name}] {key} = '{peer}', which is not "
                    f"declared (have {sorted(minions)})"
                )


def apply_overrides(
    config: RigConfig,
    assignments: list[str],
    *,
    ref_keys: frozenset[str] = frozenset(),
    path_keys: frozenset[str] = frozenset(),
) -> RigConfig:
    """Apply ``MINION.key=value`` assignments to a parsed config, in place.

    This is what a ``--set`` flag calls, and it exists because a config file is the right
    home for a rig's settings but the wrong home for a one-off: swapping a COM port to
    test a cable, or closing a GUI on a timer for an unattended run, should not be an edit
    to the file that describes the rig -- an edit that is easy to make, easy to forget to
    undo, and that the next launch inherits silently.

    `value` is read as a TOML value, so ``refresh_interval=1`` is an integer,
    ``debug_fps=true`` a boolean and ``port_name="COM5"`` a string.  A bare word that is
    not valid TOML is taken as a string, because ``port_name=COM5`` is what an operator
    types and refusing it to defend a type system nobody asked about would be pedantry.
    Quote it to be explicit.

    Only existing minions can be targeted; there is no way to add one.  An override that
    could introduce a minion would be a second, worse config format, reachable only from
    shell history.
    """
    for text in assignments:
        target, separator, raw = text.partition("=")
        if not separator:
            raise ConfigError(f"--set {text!r}: expected MINION.key=value")
        minion, dot, key = target.strip().partition(".")
        if not dot or not minion or not key:
            raise ConfigError(
                f"--set {text!r}: expected MINION.key=value, e.g. 'GUI.close_after=12' "
                f"(minions here: {sorted(config.minions)})"
            )
        spec = config.minions.get(minion)
        if spec is None:
            raise ConfigError(
                f"--set {text!r}: no [minion.{minion}] in {config.path} "
                f"(have {sorted(config.minions)})"
            )
        if key in RESERVED_KEYS:
            raise ConfigError(
                f"--set {text!r}: '{key}' configures the builder, not the compiler, and "
                f"is not overridable from the command line ({sorted(RESERVED_KEYS)})"
            )
        spec.params[key] = _substitute_nulls(_parse_toml_value(raw))
        resolve_path_keys(spec.params, path_keys, Path.cwd(), f"--set {text!r}")

    if assignments:
        validate_minion_refs(config.minions, ref_keys, str(config.path))
    return config


def _parse_toml_value(raw: str) -> Any:
    """Read one TOML value, falling back to the literal text."""
    try:
        return tomllib.loads(f"value = {raw}")["value"]
    except tomllib.TOMLDecodeError:
        return raw


def resolve_class(dotted: str) -> type:
    """Import ``"package.module:ClassName"`` and return the class.

    Kept separate from parsing so that a config file can be validated structurally
    without importing hardware drivers, and so that :func:`validate_compilers` can resolve
    every class up front -- the answer to the one real cost of moving a topology out of
    Python, which is that a mistyped class name is no longer caught by an editor.
    """
    module_name, _, class_name = dotted.partition(":")
    try:
        module = import_module(module_name)
    except ImportError as exc:
        raise ConfigError(f"cannot import module '{module_name}' for '{dotted}': {exc}") from exc
    try:
        return getattr(module, class_name)
    except AttributeError as exc:
        raise ConfigError(f"module '{module_name}' has no attribute '{class_name}'") from exc


def validate_compilers(config: RigConfig) -> dict[str, type]:
    """Resolve every compiler path before any minion is constructed.

    All of them, and report all failures together: launching eight processes and failing
    on the last one wastes a minute and leaves seven orphans behind.
    """
    resolved: dict[str, type] = {}
    problems: list[str] = []
    for name, dotted in config.compiler_paths().items():
        try:
            resolved[name] = resolve_class(dotted)
        except ConfigError as exc:
            problems.append(f"  [minion.{name}] {exc}")
    if problems:
        raise ConfigError(
            f"{config.path}: {len(problems)} compiler path(s) could not be resolved:\n"
            + "\n".join(problems)
        )
    return resolved
