"""Behavioural tests for the launcher layer: what a rig file may say, and what it builds.

This layer is the one place where a mistake is silent by construction.  Everything below
it fails loudly -- a bad state name returns None, a dead peer raises FileNotFoundError.
But a configuration file that parses *wrongly* produces an application that starts
cleanly, logs nothing unusual, and quietly does the wrong thing: a minion timed off the
wrong peer, a path resolved against the wrong directory, a calibration merged into
nothing.  So the tests here are mostly about what must be **rejected**.

Three groups:

1. **Structure** -- the errors that must not pass silently.  Each is a real failure mode
   that reached a running rig before it was checked here.
2. **Resolution** -- `log_dir`, `PATH_KEYS` and the null sentinel, which all answer the
   same question: what is a relative path in a config file relative to?  The answer has
   to be "the config file", and never "wherever the process happened to start".
3. **Building** -- that a parsed config becomes the minions it describes, with the
   parameters it gives them, and that `[app] unique_names` renames both the processes and
   every reference to them.

Group 3 constructs real APP objects but starts no process: `Application.build()` stops
short of `run()` precisely so this is possible on a machine with no hardware.

Standalone:  python tests/test_launcher.py
pytest:      pytest tests/test_launcher.py
"""

import json
import pickle
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from miniPoly.launcher import (  # noqa: E402
    Application,
    ConfigError,
    Writeback,
    apply_overrides,
    load_rig,
)

# A minimal but complete rig: one minion, a logger, a stated start order and log
# destination. Every test below is this document plus or minus one line, so a failure
# names the line that broke rather than a document that differs in several ways at once.
MINIMAL = """
[app]
logger = "LOGGER"
run_order = ["A", "LOGGER"]
log_dir = "logs"

[defaults.streaming]
timer_minion = "A"

[minion.A]
kind = "streaming"
compiler = "pkg.mod:Thing"
"""

KINDS = frozenset(Application.KINDS)


def _write(tmp, text, name="rig.toml"):
    path = Path(tmp) / name
    path.write_text(text, encoding="utf-8")
    return path


def _load(tmp, text, **kwargs):
    kwargs.setdefault("kinds", KINDS)
    kwargs.setdefault("ref_keys", Application.REF_KEYS)
    return load_rig(_write(tmp, text), **kwargs)


def _expect_error(tmp, text, fragment, label, **kwargs):
    """Assert that `text` is rejected, and that the message names the offending thing.

    The fragment matters as much as the rejection: an error that says only "invalid
    config" sends the reader back to the whole file, which for a nine-minion rig is the
    difference between a ten-second fix and a ten-minute one.
    """
    try:
        _load(tmp, text, **kwargs)
    except ConfigError as exc:
        if fragment not in str(exc):
            return [f"{label}: raised ConfigError but without {fragment!r}: {exc}"]
        return []
    return [f"{label}: accepted a config that should have been rejected"]


# ----------------------------------------------------------------------------------
# 1. Structure
# ----------------------------------------------------------------------------------

def check_structural_errors_are_rejected():
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        problems += _expect_error(
            tmp, MINIMAL.replace('run_order = ["A", "LOGGER"]', 'run_order = ["LOGGER"]'),
            "omits", "a minion missing from run_order",
        )
        problems += _expect_error(
            tmp, MINIMAL.replace('kind = "streaming"', 'kind = "strea"'),
            "kind", "an unknown kind",
        )
        problems += _expect_error(
            tmp, MINIMAL.replace('compiler = "pkg.mod:Thing"', 'compiler = "pkg.mod.Thing"'),
            "ClassName", "a compiler path without the ':' separator",
        )
        problems += _expect_error(
            tmp, MINIMAL + '\nconnect = ["Nope"]\n',
            "declared", "a connect target that does not exist",
        )
        problems += _expect_error(
            tmp, MINIMAL + '\nconnect = ["A"]\n',
            "itself", "a minion connected to itself",
        )
        problems += _expect_error(
            tmp,
            MINIMAL.replace('run_order = ["A", "LOGGER"]', 'run_order = ["A", "A", "LOGGER"]'),
            "more than once", "a duplicated entry in run_order",
        )
        # A run_order that silently omitted the logger would start every minion and never
        # drain the log queue.
        problems += _expect_error(
            tmp, MINIMAL.replace('run_order = ["A", "LOGGER"]', 'run_order = ["A"]'),
            "omits", "a run_order without the logger",
        )
        problems += _expect_error(
            tmp, MINIMAL.replace('logger = "LOGGER"', 'logger = "A"'),
            "collides", "a logger named after a declared minion",
        )
        # Omitting log_dir must fail rather than fall through to LoggerMinion's relative
        # 'logs/', which is the whole reason the key is required.
        problems += _expect_error(
            tmp, MINIMAL.replace('log_dir = "logs"', ''),
            "log_dir", "a config with no log_dir",
        )
        problems += _expect_error(
            tmp, MINIMAL.replace('[defaults.streaming]', '[defaults.streamign]'),
            "not a valid kind", "a [defaults] table for a kind that does not exist",
        )
        # Into [app], not appended: a key at the end of the document lands in the last
        # table opened, which is [minion.A], where it would be a harmless compiler kwarg.
        problems += _expect_error(
            tmp, MINIMAL.replace('logger = "LOGGER"', 'logger = "LOGGER"\nunique_names = "yes"'),
            "true or false", "unique_names given a string",
        )
    return problems


def check_a_minion_reference_must_name_a_declared_minion():
    """`timer_minion = "SCNA"` is the failure this catches, and nothing else would.

    These keys are ordinary compiler kwargs, so the connect-graph check does not see
    them. Unvalidated, the typo produces a minion that links to a peer which never
    exists, waits out the framework's retry on every tick, and reports nothing wrong --
    a rig that starts, runs, and silently never triggers.
    """
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        problems += _expect_error(
            tmp, MINIMAL.replace('timer_minion = "A"', 'timer_minion = "SCNA"'),
            "SCNA", "a timer_minion naming a minion that does not exist",
        )
        problems += _expect_error(
            tmp, MINIMAL + '\ntrigger_minion = "GUI"\n',
            "trigger_minion", "a trigger_minion naming a minion that does not exist",
        )
        # A null reference is legitimate: `timer_minion` and `trigger_minion` are
        # constructor arguments, not types, and a minion with neither is a valid rig.
        config = _load(tmp, MINIMAL + '\ntrigger_minion = "@none"\n')
        if config.minions["A"].params.get("trigger_minion", "unset") is not None:
            problems.append("a null minion reference was not left as None")
    return problems


def check_defaults_only_reach_their_own_kind():
    """timer_minion is required by every streaming minion and taken by no GUI.

    A flat [defaults] table would push it into the GUI's kwargs, where it would be
    forwarded to a compiler that never asked for it.
    """
    text = """
[app]
logger = "LOGGER"
run_order = ["S", "G", "LOGGER"]
log_dir = "logs"

[defaults.streaming]
timer_minion = "S"

[minion.S]
kind = "streaming"
compiler = "pkg.mod:Thing"

[minion.G]
kind = "gui"
compiler = "pkg.mod:Gui"
"""
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        config = _load(tmp, text)
        if "timer_minion" in config.minions["G"].params:
            problems.append("a [defaults.streaming] key reached the gui minion")
        if config.minions["S"].params.get("timer_minion") != "S":
            problems.append("a [defaults.streaming] key did not reach the streaming minion")
        # A minion's own table must win over the default, or a per-minion override would
        # be silently ignored -- the worst of the three possible behaviours.
        config = _load(tmp, text.replace(
            '[minion.S]\nkind = "streaming"', '[minion.S]\ntimer_minion = "G"\nkind = "streaming"'
        ))
        if config.minions["S"].params.get("timer_minion") != "G":
            problems.append("a [minion.X] key did not override its [defaults.<kind>] value")
    return problems


def check_every_declared_kind_resolves_to_a_real_class():
    """`Application.KINDS` names five classes as strings; all five must exist.

    Dotted strings are what keep `import miniPoly.launcher` from pulling in PyQt5 and
    vispy, and the cost of that is exactly this: a typo in the table is not caught by an
    editor. This is what pays it.
    """
    from miniPoly.launcher import resolve_class

    problems = []
    for kind, dotted in Application.KINDS.items():
        try:
            resolve_class(dotted)
        except ConfigError as exc:
            problems.append(f"KINDS[{kind!r}] = {dotted!r} does not resolve: {exc}")
    return problems


# ----------------------------------------------------------------------------------
# 2. Resolution: what is a relative path relative to?
# ----------------------------------------------------------------------------------

def check_log_dir_resolves_and_never_stays_relative():
    """A relative log_dir must resolve against the config file, not the working directory.

    This is the whole point of the key. If it came back relative, `LoggerMinion` would
    resolve it against the CWD again and the 1.3 GB would simply come back under a new
    name.
    """
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        config = _load(tmp, MINIMAL)
        if not config.log_dir.is_absolute():
            problems.append(f"a relative log_dir stayed relative: {config.log_dir}")
        elif config.log_dir != (Path(tmp) / "logs").resolve():
            problems.append(
                f"a relative log_dir resolved to {config.log_dir}, not against the "
                f"config file's directory ({(Path(tmp) / 'logs').resolve()})"
            )

        absolute = str(Path(tmp).resolve() / "elsewhere")
        config = _load(tmp, MINIMAL.replace('log_dir = "logs"', f'log_dir = {absolute!r}'))
        if config.log_dir != Path(absolute):
            problems.append(f"an absolute log_dir was rewritten: {config.log_dir} != {absolute}")
    return problems


#: `[app] path_keys` is declared by the config file itself, so the fixtures below carry it
#: in the TOML rather than passing it to `load_rig`. It was an `Application.PATH_KEYS`
#: frozenset until 1.1.0; a list of keyword names is data, so it moved into the file.
DECLARES_PATH_KEY = 'path_keys = ["stimulus_folder"]\n'


def check_path_keys_resolve_against_the_config_file_and_must_exist():
    """The bug this whole mechanism exists for, in one test.

    Every key a config puts in `[app] path_keys` was once a bare or `../`-prefixed path
    resolved by a compiler against the **process working directory** -- so it worked only
    from one folder, and moving the launcher took a minion down at startup.
    """
    problems = []
    declared = MINIMAL.replace("[app]\n", "[app]\n" + DECLARES_PATH_KEY, 1)
    if DECLARES_PATH_KEY not in declared:
        return ["the MINIMAL fixture no longer has an [app] table to declare path_keys in"]

    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "stimuli").mkdir()

        config = _load(tmp, declared + '\nstimulus_folder = "stimuli"\n')
        got = config.minions["A"].params["stimulus_folder"]
        want = str((Path(tmp) / "stimuli").resolve())
        if got != want:
            problems.append(f"stimulus_folder resolved to {got!r}, not {want!r}")
        # A string, not a Path: these reach compilers that hand them to Qt's file dialog,
        # to os.path.exists and to open(). A Path works by accident and would not after
        # any of them is concatenated.
        if not isinstance(got, str):
            problems.append(f"a resolved path key came back as {type(got).__name__}, not str")

        # The declared set also reaches --set, so `apply_overrides` resolves the same keys
        # the file's own values were resolved against. Carried on the parsed config for
        # that reason; before 1.1.0 it was a class attribute both halves read.
        if config.path_keys != frozenset({"stimulus_folder"}):
            problems.append(f"RigConfig.path_keys is {set(config.path_keys)}, not the declared set")

        # Existence is checked here rather than in the compiler's own process, which for
        # a nine-minion rig may be the eighth to start.
        problems += _expect_error(
            tmp, declared + '\nstimulus_folder = "no_such_dir"\n',
            "does not exist", "a path key naming something absent",
        )

        # A null path key is a real setting, not an omission: a shader that is not loaded
        # at startup, a database this rig does not write to.
        config = _load(tmp, declared + '\nstimulus_folder = "@none"\n')
        if config.minions["A"].params.get("stimulus_folder", "unset") is not None:
            problems.append("a null path key was not left as None")

        # A key that is not declared must pass through untouched, however path-like it
        # looks: savedir, remote_dir and netdrive_dir are a data drive, a host and a UNC
        # share, and rewriting any of them would break the rig.
        config = _load(tmp, declared + '\nsavedir = "D:\\\\data\\\\"\n')
        if config.minions["A"].params["savedir"] != "D:\\data\\":
            problems.append("an undeclared path-like key was rewritten")

        # And a config that declares nothing resolves nothing, which is the safe default:
        # resolving a key nobody asked about would turn a UNC share into a failing check.
        config = _load(tmp, MINIMAL + '\nstimulus_folder = "no_such_dir"\n')
        if config.minions["A"].params["stimulus_folder"] != "no_such_dir":
            problems.append("an undeclared path key was resolved anyway")

        problems += _expect_error(
            tmp, MINIMAL.replace("[app]\n", '[app]\npath_keys = "stimulus_folder"\n', 1),
            "must be a list", "path_keys given as a bare string",
        )
    return problems


def check_the_null_sentinel_becomes_none():
    """TOML has no null, but a compiler keyword can legitimately take None."""
    text = MINIMAL + """
[minion.A.motor_dict]
CLGAIN = "@none"
light_pin = 6
"""
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        motor_dict = _load(tmp, text).minions["A"].params["motor_dict"]
        if motor_dict.get("CLGAIN", "unset") is not None:
            problems.append(f"'@none' did not become None: {motor_dict.get('CLGAIN')!r}")
        if motor_dict.get("light_pin") != 6:
            problems.append("a neighbouring value was disturbed by the substitution")
    return problems


#: `[app.writeback]`, plus a minion that opts in and something to overlay onto. This is
#: what the `customise` hook became in 1.1.0: the hook was the one extension point, and
#: across every application built on this framework its only implementation was this
#: merge. The five names below were the only part of it that belonged to a rig.
WRITEBACK = MINIMAL.replace(
    "[defaults.streaming]",
    """[app.writeback]
key = "calibration"
target = "motor_dict"
path_param = "motor_config"
payload = "motors"
fields = ["min_pos", "offset"]

[defaults.streaming]""",
    1,
) + """calibration = "calib.json"

[minion.A.motor_dict]
light_pin = 6

[minion.A.motor_dict.axis_x]
ID = 1
min_pos = 0
"""


def _calib(tmp, entries, **extra):
    (Path(tmp) / "calib.json").write_text(
        json.dumps({**extra, "motors": entries}), encoding="utf-8"
    )


def check_the_write_back_file_is_merged_and_the_handle_injected():
    """The half of a configuration the program writes, read back and overlaid.

    Applied last, after defaults, null substitution and path keys, so a write-back file
    overlays values that are already current -- the ordering the `customise` hook this
    replaced also relied on.
    """
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        _calib(tmp, {"axis_x": {"min_pos": 11, "offset": 3.5}}, note="a human wrote this")
        spec = _load(tmp, WRITEBACK).minions["A"]
        axis = spec.params["motor_dict"]["axis_x"]

        if axis.get("min_pos") != 11:
            problems.append(f"the file did not overwrite the TOML's min_pos: {axis.get('min_pos')!r}")
        if axis.get("offset") != 3.5:
            problems.append("a field only the write-back file has was not added")
        if axis.get("ID") != 1:
            problems.append("merging clobbered a field only the TOML has")
        if spec.params["motor_dict"].get("light_pin") != 6:
            problems.append("a non-entry value in the target table was disturbed")
        if "calibration" in spec.params:
            problems.append("the opt-in key was passed through to the compiler")

        handle = spec.params.get("motor_config")
        if not isinstance(handle, Writeback):
            problems.append(f"path_param holds {type(handle).__name__}, not a Writeback")
            return problems
        if handle.path != (Path(tmp) / "calib.json").resolve():
            problems.append("the injected handle does not point at the file that was read")
        # The compiler puts this in log lines, where the two names are noise.
        if str(handle) != str(handle.path):
            problems.append("str() on the handle is not the path")

        # Frozen and carrying only a path and two names, because on Windows a minion is
        # spawned rather than forked and every parameter is pickled on the way in.
        if pickle.loads(pickle.dumps(handle)) != handle:
            problems.append("the handle does not survive a pickle round trip")

        # A minion that does not opt in is untouched, so one rig can have a calibrated
        # servo and an uncalibrated camera.
        plain = _load(tmp, WRITEBACK.replace('calibration = "calib.json"', "", 1)).minions["A"]
        if "motor_config" in plain.params:
            problems.append("a minion that declared no write-back file got a handle anyway")
    return problems


def check_the_write_back_file_saves_atomically_and_keeps_metadata():
    """The write half. Nothing else in this suite reaches it, and no rig does until an
    operator presses Save -- at which point the file is the only record of a measurement."""
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        _calib(tmp, {"axis_x": {"min_pos": 0, "offset": 0.0}}, note="keep me", rig="bench")
        handle = _load(tmp, WRITEBACK).minions["A"].params["motor_config"]

        handle.save({"axis_x": {"min_pos": 7, "offset": -1.25}})
        document = json.loads(handle.path.read_text(encoding="utf-8"))

        if document.get("motors", {}).get("axis_x", {}).get("min_pos") != 7:
            problems.append("the saved value is not on disk")
        if document.get("note") != "keep me" or document.get("rig") != "bench":
            problems.append("a machine rewrite dropped the hand-written metadata")
        if "saved" not in document:
            problems.append("no 'saved' timestamp was stamped")
        if list(Path(tmp).glob("*.tmp")):
            problems.append("the atomic write left its temporary file behind")
        if handle.load() != {"axis_x": {"min_pos": 7, "offset": -1.25}}:
            problems.append("what was written does not read back")
    return problems


def check_the_write_back_file_refuses_what_it_cannot_mean():
    """Four rejections, each preferred over a failure that surfaces far from its cause."""
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        # A field outside `fields`. A typo'd key that is quietly dropped is
        # indistinguishable from a good save.
        _calib(tmp, {"axis_x": {"offest": 1.0}})
        problems += _expect_error(tmp, WRITEBACK, "offest", "a misspelled write-back field")

        # An entry the target table does not declare. Adding it would let a stale file
        # resurrect hardware that was deliberately removed from the setup.
        _calib(tmp, {"axis_q": {"offset": 1.0}})
        problems += _expect_error(tmp, WRITEBACK, "axis_q", "an entry absent from the target")

        # Parsing stops rather than falling back to the TOML's own values, or the rig
        # would run on the wrong measurements without saying so.
        (Path(tmp) / "calib.json").unlink()
        problems += _expect_error(tmp, WRITEBACK, "not found", "a missing write-back file")

        _calib(tmp, {"axis_x": {"min_pos": 1}})
        handle = _load(tmp, WRITEBACK).minions["A"].params["motor_config"]
        try:
            handle.save({"axis_x": {"min_pos": 1, "torque": True}})
        except ConfigError as exc:
            if "torque" not in str(exc):
                problems.append(f"save rejected, but without naming the field: {exc}")
        else:
            problems.append("save accepted a field outside the declared set")

        # All five names required: a guessed payload key would write a file the reader
        # cannot read back.
        problems += _expect_error(
            tmp, WRITEBACK.replace('payload = "motors"\n', "", 1),
            "missing", "an [app.writeback] table with a name left out",
        )
        problems += _expect_error(
            tmp, WRITEBACK.replace('fields = ["min_pos", "offset"]', "fields = []", 1),
            "non-empty list", "an [app.writeback] with no fields",
        )
    return problems


# ----------------------------------------------------------------------------------
# 3. Overrides
# ----------------------------------------------------------------------------------

def check_overrides_are_typed_and_validated():
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        config = _load(tmp, MINIMAL)
        apply_overrides(
            config,
            ["A.refresh_interval=3", "A.debug=true", "A.rate=0.5", "A.port=COM5",
             "A.quoted='COM6'", "A.nothing=@none"],
            ref_keys=Application.REF_KEYS,
        )
        params = config.minions["A"].params
        for key, want in (("refresh_interval", 3), ("debug", True), ("rate", 0.5),
                          ("port", "COM5"), ("quoted", "COM6"), ("nothing", None)):
            if params.get(key, "unset") != want:
                problems.append(f"--set A.{key}: got {params.get(key)!r}, want {want!r}")
        # An int must stay an int: refresh_interval reaches a timer that multiplies it.
        if not isinstance(params["refresh_interval"], int):
            problems.append("--set read an integer as something else")

        for bad, fragment, label in (
            ("nope", "expected MINION.key=value", "an override with no '='"),
            ("A.key", "expected MINION.key=value", "an override with no value"),
            ("ZZZ.key=1", "no [minion.ZZZ]", "an override naming an absent minion"),
            ("A.kind=gui", "configures the builder", "an override of a reserved key"),
            ("A.timer_minion=NOPE", "not\n  declared", "an override breaking a reference"),
        ):
            fresh = _load(tmp, MINIMAL)
            try:
                apply_overrides(fresh, [bad], ref_keys=Application.REF_KEYS)
            except ConfigError as exc:
                # `fragment` is matched loosely: the reference error wraps across lines.
                if fragment.split("\n")[0] not in str(exc):
                    problems.append(f"{label}: message does not name the problem: {exc}")
            else:
                problems.append(f"{label}: was accepted")
    return problems


# ----------------------------------------------------------------------------------
# 4. Building: a parsed config becomes the minions it describes
# ----------------------------------------------------------------------------------

BUILDABLE = """
[app]
logger = "LOGGER"
run_order = ["GUI", "DISPLAY", "LOGGER"]
log_dir = "logs"
unique_names = %s

[minion.GUI]
kind = "gui"
compiler = "miniPoly.compiler.graphics:QtCompiler"
refresh_interval = 10
theme = "@none"
display_minion = "DISPLAY"

[minion.DISPLAY]
kind = "display"
compiler = "miniPoly.util.display:GLDisplay"
connect = ["GUI"]
refresh_interval = 10
controllerProcName = "GUI"
"""


class _BuildApp(Application):
    """No PATH_KEYS and no hook: the framework's behaviour with nothing added."""


def check_build_constructs_the_declared_minions_without_starting_them():
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        application = _BuildApp.from_file(_write(tmp, BUILDABLE % "false")).build()

        if sorted(application.minions) != ["DISPLAY", "GUI"]:
            problems.append(f"built {sorted(application.minions)}, expected ['DISPLAY', 'GUI']")
        if application.minions["GUI"].name != "GUI":
            problems.append(f"minion name is {application.minions['GUI'].name!r}, expected 'GUI'")
        if application.logger is None:
            problems.append("no logger was constructed")
        elif application.logger.name != "LOGGER":
            problems.append(f"logger is named {application.logger.name!r}, expected 'LOGGER'")

        # The kind table decided the class. Getting this wrong is not a quiet failure:
        # a display built as a plain AbstractAPP has no canvas to render into.
        from miniPoly.processor.GL import GLAPP
        from miniPoly.processor.GUI import AbstractGUIAPP

        if not isinstance(application.minions["GUI"], AbstractGUIAPP):
            problems.append("kind 'gui' did not build an AbstractGUIAPP")
        if not isinstance(application.minions["DISPLAY"], GLAPP):
            problems.append("kind 'display' did not build a GLAPP")

        # `build()` must not start anything -- that is what makes a dry run possible and
        # what lets this test run at all.
        for name, minion in application.minions.items():
            if getattr(minion, "_is_running", None) is not None and minion._is_running:
                problems.append(f"build() started {name}")

        # The log directory is created by build(), because FileHandler does not and the
        # logger is the first process to start.
        if not (Path(tmp) / "logs").is_dir():
            problems.append("build() did not create log_dir")
    return problems


def check_run_before_build_is_an_error():
    """Rather than a confusing AttributeError from an empty minion table."""
    with tempfile.TemporaryDirectory() as tmp:
        application = _BuildApp.from_file(_write(tmp, BUILDABLE % "false"))
        try:
            application.run()
        except RuntimeError:
            return []
        except Exception as exc:
            return [f"run() before build() raised {type(exc).__name__}, expected RuntimeError"]
        return ["run() before build() started an application with no minions"]


def check_unique_names_renames_the_processes_and_their_references():
    """The half that is easy to forget is the references.

    Suffixing the minions without suffixing `display_minion`/`controllerProcName` leaves
    every one of them pointing at a name that no longer exists -- and because a foreign
    read on a missing peer is a wait-and-retry rather than an exception, the application
    starts clean and simply never exchanges anything.
    """
    problems = []
    import os

    suffix = f"_{os.getpid()}"
    with tempfile.TemporaryDirectory() as tmp:
        application = _BuildApp.from_file(_write(tmp, BUILDABLE % "true")).build()

        if application.suffix != suffix:
            problems.append(f"suffix is {application.suffix!r}, expected {suffix!r}")
        # Keyed by the config name, so run_order and the connect graph need no rewriting.
        if sorted(application.minions) != ["DISPLAY", "GUI"]:
            problems.append(f"unique_names changed the dict keys: {sorted(application.minions)}")
        for name in ("GUI", "DISPLAY"):
            got = application.minions[name].name
            if got != name + suffix:
                problems.append(f"{name} process name is {got!r}, expected {name + suffix!r}")
        if application.logger.name != "LOGGER" + suffix:
            problems.append(f"logger name is {application.logger.name!r}, not suffixed")

        # `_param_to_compiler` is what every APP shell stashes its **kwargs in, and what
        # it hands to the compiler inside the child process -- so this is the value the
        # running minion will actually use to address its peer.
        gui = application.minions["GUI"]._param_to_compiler
        display = application.minions["DISPLAY"]._param_to_compiler
        if gui.get("display_minion") != "DISPLAY" + suffix:
            problems.append(
                f"display_minion is {gui.get('display_minion')!r}, not suffixed -- "
                "the GUI would address a peer that does not exist"
            )
        if display.get("controllerProcName") != "GUI" + suffix:
            problems.append(
                f"controllerProcName is {display.get('controllerProcName')!r}, not suffixed"
            )

        # And the parsed config must be untouched: it is compared against baselines and
        # printed by dry runs, both of which have to be reproducible.
        if application.config.minions["GUI"].params["display_minion"] != "DISPLAY":
            problems.append("unique_names mutated the parsed config rather than the build")

        # Without it, nothing moves.
        plain = _BuildApp.from_file(_write(tmp, BUILDABLE % "false", "plain.toml")).build()
        if plain.suffix or plain.minions["GUI"].name != "GUI":
            problems.append("unique_names = false still renamed something")
    return problems


CHECKS = (
    ("structural errors are rejected", check_structural_errors_are_rejected),
    ("a minion reference must name a declared minion",
     check_a_minion_reference_must_name_a_declared_minion),
    ("defaults only reach their own kind", check_defaults_only_reach_their_own_kind),
    ("every declared kind resolves to a real class",
     check_every_declared_kind_resolves_to_a_real_class),
    ("log_dir resolves and never stays relative",
     check_log_dir_resolves_and_never_stays_relative),
    ("path keys resolve against the config file and must exist",
     check_path_keys_resolve_against_the_config_file_and_must_exist),
    ("the null sentinel becomes None", check_the_null_sentinel_becomes_none),
    ("the write-back file is merged and its handle injected",
     check_the_write_back_file_is_merged_and_the_handle_injected),
    ("the write-back file saves atomically and keeps metadata",
     check_the_write_back_file_saves_atomically_and_keeps_metadata),
    ("the write-back file refuses what it cannot mean",
     check_the_write_back_file_refuses_what_it_cannot_mean),
    ("overrides are typed and validated", check_overrides_are_typed_and_validated),
    ("build constructs the declared minions without starting them",
     check_build_constructs_the_declared_minions_without_starting_them),
    ("run before build is an error", check_run_before_build_is_an_error),
    ("unique_names renames the processes and their references",
     check_unique_names_renames_the_processes_and_their_references),
)


def test_launcher():
    problems = []
    for label, fn in CHECKS:
        problems.extend(f"{label}: {p}" for p in fn())
    assert not problems, "\n".join(problems)


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    failed = False
    for label, fn in CHECKS:
        found = fn()
        if found:
            failed = True
            print(f"FAIL {label}")
            for problem in found:
                print(f"       {problem}")
        else:
            print(f"OK   {label}")
    raise SystemExit(1 if failed else 0)
