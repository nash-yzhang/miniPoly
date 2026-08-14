"""The three steps between a command line and a running application.

Every application built on this framework answers the same three questions -- which config
file, which values to override for this run only, and whether to actually start anything --
and then does the same three things with the answers.  That was written once per
application, then factored into a module shared by two of them, and is now here, which is
where it stopped being either application's business: nothing in this file names a rig, a
minion or a device.

Deliberately free of any CLI library.  A command-line front end is one caller of this, not
the only conceivable one, and a module that describes configuration should not oblige an
application to install an argument parser to use it.  So the failure mode is
:class:`~miniPoly.launcher.config.ConfigError`, and printing is `print`; a front end that
wants a tidy usage message catches the one and formats it however it likes.
"""

from __future__ import annotations

from pathlib import Path

from miniPoly.launcher.application import Application
from miniPoly.launcher.config import ConfigError

#: Help text for the two options every front end offers, kept here so that two of them
#: describe the same behaviour in the same words.  They document what `launch_config` and
#: `apply_overrides` do, which is this layer's to explain, not each application's.
SET_HELP = (
    "override a config value for this run only, as MINION.key=value "
    "(repeatable; the value is read as TOML)"
)
DRY_RUN_HELP = "build the application and report it, without starting any process"


def resolve_config(path: str | Path | None, default: str | Path) -> Path:
    """Return the config file to launch, or fail naming the alternatives.

    The second line of the error is the reason this is not left to the caller's argument
    parser, which would say "does not exist" and stop.  A stale path is almost always a
    renamed or moved config, and the answer someone needs at that moment is the list of the
    ones that *do* exist -- which only the directory knows.
    """
    default = Path(default)
    chosen = default if path is None else Path(path)
    if chosen.is_file():
        return chosen
    available = sorted(p.name for p in default.parent.glob("*.toml"))
    raise ConfigError(
        f"config file not found: {chosen}\n"
        f"  available in {default.parent}: {', '.join(available) or 'none'}"
    )


def launch_config(
    config: str | Path,
    overrides: list[str] | None = None,
    dry_run: bool = False,
) -> Application | None:
    """Load, override, build and -- unless this is a dry run -- start an application.

    Returns the built application, or None after a dry run has reported one.  Raises
    :class:`~miniPoly.launcher.config.ConfigError` for anything wrong with the file, which
    is the caller's to present: a malformed config is someone's typo to fix, not a bug to
    report, so it deserves one line rather than a traceback through the loader.
    """
    application = Application.from_file(config, overrides).build()
    if dry_run:
        report(application)
        return None
    application.run()
    return application


def report(application: Application) -> None:
    """Print what `build()` produced: the check a dry run exists to make possible.

    `build()` resolves every compiler class, applies every default, overlays any write-back
    file and constructs every minion -- all without starting a process.  So this runs the
    entire launch except the launch, on a laptop with no hardware, and prints the parameters
    each process would have been given.
    """
    config = application.config
    print(f"{config.path}")
    print(f"  log_dir    {config.log_dir}")
    print(f"  run_order  {' -> '.join(config.run_order)}")
    if application.suffix:
        print(f"  names      suffixed with {application.suffix!r} ([app] unique_names)")
    for name in config.run_order:
        if name == config.logger_name:
            print(f"  [{name}] the logger")
            continue
        spec = config.minions[name]
        print(f"  [{name}] {spec.kind} <- {spec.compiler}")
        if spec.connect:
            print(f"      connect {', '.join(spec.connect)}")
        for key, value in sorted(spec.params.items()):
            print(f"      {key} = {value!r}")
    print("built; no process started (--dry-run)")
