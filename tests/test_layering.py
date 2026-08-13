"""Layer-dependency boundary test (purely static; imports nothing under test).

Uses `ast` rather than importing, so it runs on machines without pyusb or
vispy.

Layer rules, per docs/architecture.md, which is the living statement of the rule.

    core        <- nothing (stdlib and third party only)
    compiler    <- core, definition
    contrib     <- core, compiler          (rig-specific, outside the contract)
    processor   <- core                    (must know nothing about compilers)
    util        <- core
    launcher    <- core, processor         (composes APPs; nothing may import it)

`processor -> compiler` is explicitly forbidden: the whole premise of the
APP/Compiler split is that the processor layer receives a compiler class as a
parameter (see processor/prototypes.py) instead of importing one itself.

`launcher` is the one layer above `processor`. It builds a set of APPs from a
config file, so it must know about them; the direction that matters is that no
other layer may import `launcher`, which is what keeps "how an application is
assembled" out of the parts being assembled. It reaches `processor` only for
`LoggerMinion` -- every other APP class is named as a dotted string and resolved
at build time, so importing `launcher` does not import PyQt5 or vispy.

Standalone:  python tests/test_layering.py
pytest:      pytest tests/test_layering.py
"""

import ast
import pathlib

PKG_ROOT = pathlib.Path(__file__).resolve().parent.parent / "miniPoly"

ALLOWED = {
    "core": set(),
    "compiler": {"core", "definition"},
    "contrib": {"core", "compiler"},
    "processor": {"core"},
    "util": {"core"},
    "launcher": {"core", "processor"},
    "definition": set(),
    "__init__": set(),  # miniPoly/__init__.py is expected to stay empty
    # The archive directory is exempt from the layer rules.
    "__arc__": {"core", "compiler", "contrib", "processor", "util", "definition"},
}


def _layer_of(path: pathlib.Path) -> str:
    """miniPoly/compiler/graphics.py -> 'compiler'; miniPoly/definition.py -> 'definition'"""
    rel = path.relative_to(PKG_ROOT)
    return rel.parts[0] if len(rel.parts) > 1 else rel.stem


def _imported_layers(path: pathlib.Path):
    """Yield (imported layer, line number, source statement) for intra-package imports."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    src_layer = _layer_of(path)

    for node in ast.walk(tree):
        target = None
        if isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                # Relative import. level == 1 means same layer, so no crossing.
                if node.level == 1:
                    continue
                # level >= 2 leaves this layer; resolve to the module under the parent
                target = (node.module or "").split(".")[0]
            elif node.module and node.module.split(".")[0] == "miniPoly":
                parts = node.module.split(".")
                target = parts[1] if len(parts) > 1 else None
        elif isinstance(node, ast.Import):
            for alias in node.names:
                parts = alias.name.split(".")
                if parts[0] == "miniPoly" and len(parts) > 1:
                    yield parts[1], node.lineno, alias.name
            continue

        if target and target != src_layer:
            yield target, node.lineno, ast.unparse(node)


def collect_violations():
    violations = []
    for path in sorted(PKG_ROOT.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        src_layer = _layer_of(path)
        if src_layer not in ALLOWED:
            violations.append((path, 0, f"unknown layer {src_layer!r}; register it in ALLOWED"))
            continue
        for dst_layer, lineno, stmt in _imported_layers(path):
            if dst_layer not in ALLOWED[src_layer]:
                violations.append(
                    (path, lineno, f"{src_layer} -> {dst_layer} is not allowed: {stmt}")
                )
    return violations


def test_no_layering_violations():
    violations = collect_violations()
    if violations:
        lines = [
            f"  {p.relative_to(PKG_ROOT.parent)}:{ln}  {msg}" for p, ln, msg in violations
        ]
        raise AssertionError(
            "%d layer dependency violation(s):\n%s" % (len(violations), "\n".join(lines))
        )


def test_processor_never_imports_compiler():
    """Pin down the most important rule on its own: processor knows no compilers."""
    offenders = []
    for path in sorted((PKG_ROOT / "processor").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        for dst, lineno, stmt in _imported_layers(path):
            if dst in {"compiler", "contrib"}:
                offenders.append(f"  {path.name}:{lineno}  {stmt}")
    assert not offenders, (
        "the processor layer must not import compiler/contrib -- a compiler class "
        "should be passed in as a parameter:\n" + "\n".join(offenders)
    )


if __name__ == "__main__":
    import sys

    # The Windows console defaults to cp1252; force UTF-8 so output never dies.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    v = collect_violations()
    if v:
        print(f"FAIL: {len(v)} violation(s)")
        for p, ln, msg in v:
            print(f"  {p.relative_to(PKG_ROOT.parent)}:{ln}  {msg}")
        raise SystemExit(1)
    print("OK   layer dependencies: no violations")
    test_processor_never_imports_compiler()
    print("OK   processor does not import compiler/contrib")
