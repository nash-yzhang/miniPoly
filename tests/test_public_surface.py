"""Public API surface tests -- keep the refactor from breaking downstream.

Two layers of protection with different jobs:

1. test_consumer_contract  -- [HARD CONTRACT, must never break]
   CONSUMER_CONTRACT is the full set of (module, name) pairs mechanically extracted
   from the real import statements in miniPolyApp. If any one of them fails to
   resolve, the application is broken. After moving classes, splitting modules or
   switching to lazy imports, this test must still be green -- it is the mechanism
   that enforces the "no behaviour change" constraint.

2. test_surface_snapshot  -- [SOFT SNAPSHOT, may be updated deliberately]
   Records the set of public names in dir() per module under tests/surface/.
   Its purpose is to turn "this export-surface change was intentional" into an
   explicit action (for example Step 8 deliberately narrows miniPoly.compiler by
   replacing star imports with lazy explicit ones). When a change is intended,
   regenerate with UPDATE_SURFACE=1 and say why in the commit message.

This file really imports the library, so it needs vispy / cv2 / pyusb / pyfirmata2
/ pyserial and, on Windows, the TIS camera DLLs. Missing pieces cause the affected
case to skip rather than fail.

Standalone:  python tests/test_public_surface.py
pytest:      pytest tests/test_public_surface.py
"""

import importlib
import os
import pathlib

SURFACE_DIR = pathlib.Path(__file__).resolve().parent / "surface"

# ---------------------------------------------------------------------------
# 1. Hard contract: every name miniPolyApp actually uses.
#
#    Produced by an ast scan of ImportFrom/Import across the miniPolyApp
#    repository root (excluding __arc__ and drafts).
#
#    NOTE the scan must start at the repository root, not at CaImg_App: GL_test/
#    sits beside CaImg_App and also imports miniPoly. Scanning only CaImg_App is
#    what once led to miniPoly/util/display.py being wrongly judged dead and
#    archived -- GL_test/renderer/* import GLRenderer from it.
#
#    Register new downstream consumers here; deleting an entry declares that
#    compatibility with that consumer is being dropped.
# ---------------------------------------------------------------------------
CONSUMER_CONTRACT = {
    "miniPoly.compiler": [
        "AbstractCameraCompiler",
        "AbstractCompiler",
        # MotorShieldCompiler and TISCameraCompiler both moved out of miniPoly
        # entirely (to CaImg_App.core.motorshield / .tiscamera in the
        # miniPolyApp repository) rather than into miniPoly.contrib -- neither
        # has a consumer other than miniPolyApp, so quarantining them inside
        # the library bought nothing. AbstractCameraCompiler is the
        # rig-agnostic half of the old TISCameraCompiler that stayed.
        "OMSDuo",
        "OMSInterface",
        "QtCompiler",
    ],
    "miniPoly.compiler.graphics": ["QtCompiler", "ShaderStreamer"],
    "miniPoly.compiler.prototypes": ["AbstractCompiler", "StreamingCompiler"],
    "miniPoly.compiler.serial_devices": ["OMSDuo", "OMSInterface"],
    "miniPoly.processor.GUI": ["AbstractGUIAPP"],
    "miniPoly.processor.GL": ["GLAPP"],
    "miniPoly.processor.Logging": ["LoggerMinion"],
    "miniPoly.processor.Streaming": ["StreamingAPP", "StreamingGLAPP"],
    "miniPoly.processor.prototypes": ["AbstractAPP"],
    # The launcher layer. `Application` is subclassed by every application in
    # miniPolyApp -- CaImg_App.launcher.application and GL_App.launcher.application --
    # and its class attributes (KINDS, REF_KEYS, PATH_KEYS) are the contract those
    # subclasses declare against, so narrowing any of them is a downstream break.
    "miniPoly.launcher": [
        "Application",
        "ConfigError",
        "MinionSpec",
        "RigConfig",
        "apply_overrides",
        "load_rig",
    ],
    "miniPoly.launcher.application": ["Application"],
    "miniPoly.launcher.config": [
        "ConfigError",
        "MinionSpec",
        "NULL_SENTINEL",
        "RigConfig",
        "apply_overrides",
        "load_rig",
        "resolve_class",
        "validate_compilers",
    ],
    "miniPoly.util": ["qnum"],
    "miniPoly.util.gui": ["DataframeModel", "DataframeTable"],
    "miniPoly.util.qnum": [],  # imported as a whole module
    # Used by miniPolyApp/GL_test/renderer/* -- five files. Do not archive
    # miniPoly/util/display.py without checking these first.
    "miniPoly.util.display": [
        "GLDisplay",
        "GLRenderer",
        "DEFAULT_SPHERE_VS",
        "DEFAULT_SPHERE_FS",
    ],
}

# Modules covered by the snapshot (the __arc__ archive is excluded).
SNAPSHOT_MODULES = [
    "miniPoly.core.buffer",
    "miniPoly.core.minion",
    "miniPoly.compiler",
    "miniPoly.compiler.prototypes",
    "miniPoly.compiler.graphics",
    "miniPoly.compiler.cameras",
    "miniPoly.compiler.serial_devices",
    "miniPoly.processor.prototypes",
    "miniPoly.processor.Streaming",
    "miniPoly.processor.GUI",
    "miniPoly.processor.Logging",
    "miniPoly.util.gui",
    "miniPoly.util.qnum",
    "miniPoly.util.display",
    "miniPoly.launcher",
    "miniPoly.launcher.config",
    "miniPoly.launcher.application",
]


def _try_import(name):
    """Return (None, reason) on import failure so callers can skip."""
    try:
        return importlib.import_module(name), None
    except Exception as exc:  # ImportError / OSError(DLL) / ...
        return None, f"{type(exc).__name__}: {exc}"


def _public_names(module):
    return sorted(n for n in dir(module) if not n.startswith("_"))


def check_consumer_contract():
    """Return (failures, skipped).

    Mind the `from pkg import submodule` case: hasattr(pkg, name) is False until the
    submodule is loaded, even though the import statement itself is valid. So a
    hasattr miss is retried as a submodule import.
    """
    failures, skipped = [], []
    for mod_name, names in CONSUMER_CONTRACT.items():
        mod, reason = _try_import(mod_name)
        if mod is None:
            skipped.append((mod_name, reason))
            continue
        for name in names:
            if hasattr(mod, name):
                continue
            sub, sub_reason = _try_import(f"{mod_name}.{name}")
            if sub is None:
                failures.append(f"{mod_name}.{name} does not resolve ({sub_reason})")
    return failures, skipped


def check_surface_snapshot(update=False):
    """Return (diffs, skipped, written). With update=True the snapshots are rewritten."""
    diffs, skipped, written = [], [], []
    SURFACE_DIR.mkdir(exist_ok=True)
    for mod_name in SNAPSHOT_MODULES:
        mod, reason = _try_import(mod_name)
        if mod is None:
            skipped.append((mod_name, reason))
            continue
        got = _public_names(mod)
        snap = SURFACE_DIR / f"{mod_name}.txt"
        if not snap.exists():
            snap.write_text("\n".join(got) + "\n", encoding="utf-8")
            written.append(mod_name)
            continue
        want = [ln for ln in snap.read_text(encoding="utf-8").splitlines() if ln]
        if got != want:
            if update:
                snap.write_text("\n".join(got) + "\n", encoding="utf-8")
                written.append(mod_name)
            else:
                diffs.append(
                    (mod_name, sorted(set(want) - set(got)), sorted(set(got) - set(want)))
                )
    return diffs, skipped, written


def test_consumer_contract():
    failures, _ = check_consumer_contract()
    assert not failures, (
        "the import contract of downstream miniPolyApp is broken:\n  "
        + "\n  ".join(failures)
    )


def test_surface_snapshot():
    diffs, _, _ = check_surface_snapshot(update=bool(os.environ.get("UPDATE_SURFACE")))
    if diffs:
        lines = []
        for mod, removed, added in diffs:
            lines.append(f"  {mod}")
            if removed:
                lines.append(f"      removed: {removed}")
            if added:
                lines.append(f"      added:   {added}")
        raise AssertionError(
            "the public export surface changed. If the narrowing/widening was "
            "intended, regenerate with UPDATE_SURFACE=1 and explain why in the "
            "commit message:\n" + "\n".join(lines)
        )


if __name__ == "__main__":
    import sys

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    update = bool(os.environ.get("UPDATE_SURFACE"))
    rc = 0

    failures, skipped = check_consumer_contract()
    if failures:
        rc = 1
        print(f"FAIL consumer contract: {len(failures)} problem(s)")
        for f in failures:
            print(f"  {f}")
    else:
        print(
            "OK   consumer contract: all %d module(s) resolved"
            % (len(CONSUMER_CONTRACT) - len(skipped))
        )
    for m, r in skipped:
        print(f"SKIP {m}  ({r})")

    diffs, skipped2, written = check_surface_snapshot(update=update)
    if diffs:
        rc = 1
        print(f"FAIL export surface: {len(diffs)} module(s) changed")
        for mod, removed, added in diffs:
            print(f"  {mod}")
            if removed:
                print(f"      removed: {removed}")
            if added:
                print(f"      added:   {added}")
    n_checked = len(SNAPSHOT_MODULES) - len(skipped2) - len(written)
    if written:
        print(f"NEW  wrote export-surface snapshots for {len(written)} module(s)")
    if n_checked:
        print(f"OK   export surface: {n_checked} module(s) unchanged")

    raise SystemExit(rc)
