"""The same rig as `two_minions.py`, built from a configuration file instead.

Run it with `uv run python examples/two_minions_config.py`. The output is identical --
same three processes, same states, same shutdown -- because the topology is identical.
Only where it is written down has changed.

Compare the two files. `two_minions.py` ends with fourteen lines that construct, connect,
attach and run; this one ends with a class that declares nothing and a single call. Those
fourteen lines are the same in every application ever built on miniPoly, so they carry no
information about *this* rig -- but they are where a new minion is most easily forgotten,
because forgetting one produces a process that starts, logs nothing, and is never linked
to its peers.

What is left for an application to say is the class below, and for this rig it is empty.
A real one declares a little more:

    class MyRig(Application):
        #: Compiler keywords holding a path that ships beside the config file, resolved
        #: against it. Everything else passes through exactly as written.
        PATH_KEYS = frozenset({"stimulus_folder", "shader_path"})

        @classmethod
        def customise(cls, spec, config_dir):
            #: Whatever merging is this application's business and no other's --
            #: overlaying a machine-written calibration onto the values a human wrote,
            #: say. Called once per minion, after everything generic has happened.
            ...
"""

from pathlib import Path

from miniPoly.launcher import Application

# Imported for its side effect on `sys.path`, not for a name: the config file addresses
# the compilers as "examples.two_minions:Sensor", so `examples` has to be importable.
# In a real application the compilers live in an installed package and this is unneeded.
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

CONFIG = Path(__file__).resolve().parent / "two_minions.toml"


class TwoMinions(Application):
    """This rig adds nothing to the framework, so there is nothing here to write."""


if __name__ == '__main__':
    # Parse, validate, resolve every compiler, construct, connect, attach the logger --
    # then start the processes in the configured order. Everything except the last step
    # happens without starting anything, which is what makes `--dry-run` possible in a
    # real CLI: build the whole application on a laptop and inspect it.
    TwoMinions.launch(CONFIG)
