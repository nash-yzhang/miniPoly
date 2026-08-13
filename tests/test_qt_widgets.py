"""``util/gui.py``'s Qt models, exercised rather than merely imported.

Added 2026-08-06. ``DataframeModel`` is how every ``.xlsx`` protocol reaches the screen in
miniPolyApp, and until now the only test touching this module was the ``dir()`` snapshot
in ``test_public_surface.py`` -- which cannot tell whether a single cell renders.

What that missed: ``data()`` read a cell as ``self._data.iloc[row][col]``. The first
subscript yields a Series indexed by column *name*; subscripting that with an integer
worked only through the positional fallback pandas removed in 3.0. On pandas 3 every cell
of every string-headed table -- which is every protocol file -- raised ``KeyError``, and
because Qt calls ``data()`` from the paint path the failure arrived as a wall of
tracebacks with the table still on screen.

No QApplication is created: ``QAbstractTableModel`` is a QObject, not a widget, so these
run headless with no platform plugin at all.
"""

import sys

import numpy as np
import pandas as pd
from PyQt5 import QtCore as qc

from miniPoly.util.gui import DataframeModel

# Mixed dtypes and string headers, i.e. shaped like a real protocol file: a float time
# column, ints, and a text column.
FRAME = pd.DataFrame(
    {
        "time": [0.0, 1.5, 3.0],
        "dynamotor_x": [10.0, 11.5, np.nan],
        "light_pin": [0, 1, 0],
        "phase_name": ["start", "sweep", "end"],
    }
)


def check_every_cell_renders():
    """Each cell must come back as ``str`` of the value at that row and column."""
    problems = []
    model = DataframeModel(FRAME)
    for row in range(len(FRAME)):
        for col in range(len(FRAME.columns)):
            index = model.index(row, col)
            try:
                shown = model.data(index, qc.Qt.DisplayRole)
            except Exception as exc:
                problems.append(f"cell ({row}, {col}) raised {type(exc).__name__}: {exc}")
                continue
            expected = str(FRAME.iloc[row, col])
            if shown != expected:
                problems.append(f"cell ({row}, {col}) shows {shown!r}, expected {expected!r}")
    return problems


def check_a_transposed_read_is_not_what_it_returns():
    """Rows and columns must not be swapped -- the shape alone would not notice."""
    problems = []
    model = DataframeModel(FRAME)
    if model.data(model.index(1, 0), qc.Qt.DisplayRole) != str(FRAME.iloc[1, 0]):
        problems.append("row 1 column 0 does not match the frame")
    if model.data(model.index(0, 3), qc.Qt.DisplayRole) != "start":
        problems.append("the text column does not render at row 0")
    return problems


def check_counts_and_headers():
    problems = []
    model = DataframeModel(FRAME)
    if model.rowCount() != len(FRAME):
        problems.append(f"rowCount is {model.rowCount()}, expected {len(FRAME)}")
    if model.columnCount() != len(FRAME.columns):
        problems.append(f"columnCount is {model.columnCount()}, expected {len(FRAME.columns)}")
    for col, name in enumerate(FRAME.columns):
        shown = model.headerData(col, qc.Qt.Horizontal, qc.Qt.DisplayRole)
        if shown != name:
            problems.append(f"header {col} is {shown!r}, expected {name!r}")
    if model.headerData(0, qc.Qt.Vertical, qc.Qt.DisplayRole) is not None:
        problems.append("only horizontal headers are provided; the vertical one must be None")
    return problems


def check_a_non_display_role_and_an_invalid_index_give_none():
    """Qt asks for many roles per cell; anything but DisplayRole must be None."""
    problems = []
    model = DataframeModel(FRAME)
    if model.data(model.index(0, 0), qc.Qt.ToolTipRole) is not None:
        problems.append("a non-display role must return None")
    if model.data(qc.QModelIndex(), qc.Qt.DisplayRole) is not None:
        problems.append("an invalid index must return None")
    return problems


CHECKS = (
    ("every cell renders", check_every_cell_renders),
    ("rows and columns are not swapped", check_a_transposed_read_is_not_what_it_returns),
    ("counts and headers", check_counts_and_headers),
    ("other roles and invalid indexes give None", check_a_non_display_role_and_an_invalid_index_give_none),
)


def test_dataframe_model():
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
            for p in found:
                print(f"       {p}")
        else:
            print(f"OK   {label}")
    raise SystemExit(1 if failed else 0)
