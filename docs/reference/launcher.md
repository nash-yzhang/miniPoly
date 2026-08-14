# launcher

What an application *is*, and how it starts.

Every other layer describes a part — a process, the logic inside one, the shell that
pairs them. This one describes a *set* of them:

> **An application is a TOML file.**

The file names the minions, their compilers, the connect graph, the start order, the log
destination, which of its keywords hold a path beside it, and which of its values the
running program writes back. There is no class to write:

```python
from miniPoly.launcher import Application

Application.launch("config/my_rig.toml")
```

Or, from a command line, with `--dry-run` and `MINION.key=value` overrides handled for you:

```python
from miniPoly.launcher import launch_config

launch_config("config/my_rig.toml", ["SENSOR.refresh_interval=5"], dry_run=True)
```

!!! warning "Changed in 1.1"
    `Application` used to be a base class, and an application subclassed it to declare
    `PATH_KEYS` and a `customise` hook. **Both are gone.** They only ever held lists of
    names, which are now `[app] path_keys` and `[app.writeback]` in the config file itself.
    If you have a subclass, delete it and move those two declarations into your TOML —
    see [the two tables below](#the-two-tables-that-replaced-the-subclass). `KINDS` and
    `REF_KEYS` stay on the class: every entry in them is a miniPoly class or a miniPoly
    keyword, so they are the same for every application.

## The three things you call

| | |
|---|---|
| `Application.launch(path, overrides=None)` | parse, build, start. The whole thing, in one call |
| `Application.from_file(path, overrides=None)` | parse and instantiate, without building or starting — for a test that wants to inspect a config |
| `launch_config(path, overrides=None, dry_run=False)` | what a command-line front end wants: the above plus `--dry-run` reporting |

`.build()` resolves every compiler class, applies every default, overlays any write-back
file and constructs every minion **without starting a process**, which is what makes a dry
run possible: the entire launch except the launch, on a laptop with no hardware.

## The two tables that replaced the subclass

### `[app] path_keys`

Compiler keywords whose value is a file or directory shipping *beside the config file*,
resolved against it and checked for existence before any process starts.

```toml
[app]
path_keys = ["stimulus_folder", "shader_path"]
```

A list rather than a rule, because every obvious rule is wrong: matching a `_dir`/`_folder`
suffix would also catch a data drive, a remote host and a UNC share, which must pass
through exactly as written. Adding a key is a deliberate act.

The check is here rather than in the compiler because a compiler that raises on a missing
file does so in *its own* process — possibly the eighth to start, after a camera has
already opened. Failing at parse time costs a second and names the file.

### `[app.writeback]`

The half of a configuration the *program* writes rather than a human: a measurement the
running application saves and reads back next time. It lives in its own JSON file, because
`tomllib` cannot write and a machine-rewritten TOML loses the comments that ports and
network paths most need.

```toml
[app.writeback]
key        = "calibration"   # the [minion.X] key that opts in; its value is the JSON file
target     = "motor_dict"    # the parameter the loaded entries are overlaid onto
path_param = "motor_config"  # the parameter the Writeback handle is injected as
payload    = "motors"        # the top-level key inside the JSON holding the entries
fields     = ["min_pos", "max_pos", "offset"]   # the only per-entry fields it may carry
```

See [How-to: config the program writes back](../howto/config-the-program-writes-back.md)
for the whole round trip, including what the compiler does with the injected handle.

## Why the config file, not Python

`config.py` is stdlib-only and imports no miniPoly, so a configuration can be parsed and
validated where the framework is not installed. `run.py` imports no CLI library, for the
same kind of reason: describing a configuration should not oblige an application to install
an argument parser. And `Application.KINDS` names its APP classes as dotted strings rather
than importing them, so `import miniPoly.launcher` costs neither PyQt5 nor VisPy.

## miniPoly.launcher.application

::: miniPoly.launcher.application

## miniPoly.launcher.config

::: miniPoly.launcher.config

## miniPoly.launcher.run

::: miniPoly.launcher.run
