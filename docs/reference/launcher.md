# launcher

What an application *is*, and how it starts.

Every other layer describes a part — a process, the logic inside one, the shell that
pairs them. This one describes a *set* of them: a TOML file naming the minions, their
compilers, the connect graph, the start order and the log destination, plus an
`Application` subclass declaring the handful of things a file cannot say about itself.

Subclass `Application`; its three class attributes are the contract.

```python
from miniPoly.launcher import Application

class MyRig(Application):
    #: Compiler keywords holding a path that ships beside the config file. Resolved
    #: against it, and checked for existence, before any process starts.
    PATH_KEYS = frozenset({"stimulus_folder", "shader_path"})

MyRig.launch("config/my_rig.toml")
```

`config.py` is stdlib-only and imports no miniPoly, so a configuration can be parsed and
validated where the framework is not installed. `Application.KINDS` names its APP classes
as dotted strings rather than importing them, so `import miniPoly.launcher` costs neither
PyQt5 nor VisPy.

## miniPoly.launcher.application

::: miniPoly.launcher.application

## miniPoly.launcher.config

::: miniPoly.launcher.config
