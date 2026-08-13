import os

import PyQt5.QtWidgets as qw
import PyQt5.QtCore as qc
import traceback, sys
from importlib import util

import pandas as pd

from miniPoly.core.minion import BaseMinion, AbstractMinionMixin

class CustomizableCloseEventWidget(qw.QWidget):
    """A QWidget whose close behavior is delegated to an externally supplied callback."""

    def set_close_event(self, func):
        """Register `func` as the handler consulted by `closeEvent` on window close."""
        self.customCloseEvent = func

    def closeEvent(self, event):
        """Qt close handler: accept or ignore the event based on `customCloseEvent`'s return value."""
        result = self.customCloseEvent(event)
        if result:
            event.accept()
        else:
            event.ignore()


class BaseGUI(qw.QMainWindow, AbstractMinionMixin):
    """
    Base class serving as an compiler between "minion" core handler and Qt GUI
    """

    def __init__(self, processHandler: BaseMinion = None, windowSize=(400, 400), rendererPath=None):
        """Wire this window to its owning minion and load the initial renderer, if any.

        `processHandler` is the minion used for logging and for forwarding scripts to
        the display process; `rendererPath`, if given, is loaded via `load_renderer`
        once the menu/window chrome has been built.
        """
        super().__init__()
        self._processHandler = processHandler
        self._windowSize = windowSize

        self._displayProcName = ''
        self.rendererName = ''
        self._renderer_path = ''
        # What `_load` last actually imported, as opposed to what has merely been
        # requested: `load_renderer` overwrites `_renderer_path` before calling `_load`,
        # so this is the only thing left to tell a reload from a first load.
        self._loaded_renderer_path = ''

        self._init_main_win()
        self._init_menu()

        self.load_renderer(rendererPath)

    def _init_main_win(self):
        """Set the window title and initial size."""
        self.setWindowTitle("Main")
        self.resize(*self._windowSize)

    def _init_menu(self):
        """Build the File/Display menus and the central widget/layout they act on."""
        self._menubar = self.menuBar()
        self._menu_file = self._menubar.addMenu('File')
        self._menu_display = self._menubar.addMenu('Display')
        loadfile = qw.QAction("Load", self)
        loadfile.setShortcut("Ctrl+O")
        loadfile.setStatusTip("Load renderer script")
        loadfile.triggered.connect(self.loadfile)
        reload = qw.QAction("Reload", self)
        reload.setShortcut("Ctrl+R")
        reload.setStatusTip("Reload renderer")
        reload.triggered.connect(self.reload)
        Exit = qw.QAction("Quit", self)
        Exit.setShortcut("Ctrl+Q")
        Exit.setStatusTip("Exit program")
        Exit.triggered.connect(self.close)
        self._menu_file.addAction(loadfile)
        self._menu_file.addAction(Exit)
        restartDisplay = qw.QAction("Restart Display", self)
        restartDisplay.setShortcut("Ctrl+Shift+R")
        restartDisplay.setStatusTip("Restart display core")
        restartDisplay.triggered.connect(self.restartDisplay)
        haltDisplay = qw.QAction("Suspend Display", self)
        haltDisplay.setShortcut("Ctrl+Shift+H")
        haltDisplay.setStatusTip("Suspend display core")
        haltDisplay.triggered.connect(self.suspendDisplay)
        self._menu_display.addAction(restartDisplay)
        self._menu_display.addAction(haltDisplay)
        self.central_widget = qw.QWidget()  # define central widget
        self.setCentralWidget(self.central_widget)

        self.boxlayout = qw.QVBoxLayout()
        self.central_widget.setLayout(self.boxlayout)
        self.init_default_custom_widget()
        # self.canvasLabel = qw.QLabel("Load stimulus via File (Ctrl+O)")
        # self.canvasLabel.setAlignment(qc.Qt.AlignCenter)
        # self.boxlayout.addWidget(self.canvasLabel)
        # self.customWidget = None

    def init_default_custom_widget(self):
        """Reset the custom widget slot to a placeholder label prompting the user to load a script."""
        self.customWidget = qw.QWidget()  # define custom widget
        self.customWidgetLayout = qw.QVBoxLayout()
        self.customWidget.setLayout(self.customWidgetLayout)
        self.canvasLabel = qw.QLabel("Load stimulus via File (Ctrl+O)")
        self.canvasLabel.setAlignment(qc.Qt.AlignCenter)
        self.customWidget.layout().addWidget(self.canvasLabel)
        self.boxlayout.addWidget(self.customWidget)

    @property
    def display_proc(self):
        """Return the name of the display-process minion this GUI forwards renderer scripts to."""
        return self._displayProcName

    @display_proc.setter
    def display_proc(self, display_proc_name):
        """Set the target display-process minion and immediately forward the current renderer to it."""
        self._displayProcName = display_proc_name
        self._load()

    def load_renderer(self, renderer_path):
        """Point the GUI at a renderer script and (re)load it, or log an error if no path was given.

        Called from `__init__` with the initial `rendererPath`, and from `loadfile`
        after the file-picker returns a path; an empty/None path means the caller had
        nothing to load (e.g. the dialog was cancelled) rather than a real error.
        """
        if renderer_path:
            self._renderer_path = renderer_path
            self._load()
        else:
            self._processHandler.error("Undefined renderer path")

    def _load(self):
        """Import the renderer module and forward it to the display process.

        Derives `rendererName` from the path -- `importModuleFromPath` registers the
        module in `sys.modules` under that name, so leaving it empty would file every
        renderer ever loaded under the same `''` key -- reimports the script, then sends
        the path to `_displayProcName` over IPC and swaps in the module's `Widget` as the
        custom control panel if it defines one. This is the common endpoint reached by
        `load_renderer`, `reload`, and the `display_proc` setter. Any failure (missing
        handler, bad script, IPC error) is caught and logged rather than raised, so a
        bad reload never kills the GUI process.
        """
        try:
            if self._displayProcName:
                if self._renderer_path:
                    is_reload = self._renderer_path == self._loaded_renderer_path
                    self.rendererName = os.path.splitext(os.path.basename(self._renderer_path))[0]
                    self.importModuleFromPath()
                    self._loaded_renderer_path = self._renderer_path
                    if is_reload:
                        self._processHandler.info("Reloaded rendering script {}".format(self._renderer_path))
                    else:
                        self._processHandler.info("Loaded rendering script: {}".format(self._renderer_path))
                    self._processHandler.info(
                        "Forwarding script [{}] to [{}]".format(self._renderer_path, self._displayProcName))
                    self.send(self._displayProcName, 'rendering_script', self._renderer_path)
                    # Load GUI
                    if self.customWidget is not None:
                        self.customWidget.close()
                        self.boxlayout.removeWidget(self.customWidget)
                        self.customWidget.setParent(None)
                        self.customWidget = None
                    if hasattr(self.imported, 'Widget'):
                        self.customWidget = self.imported.Widget(self)
                        self.boxlayout.addWidget(self.customWidget)
                else:
                    self._processHandler.log("Display core undefined")
        except Exception:
            self._processHandler.error(traceback.format_exc())

    def loadfile(self):
        """Prompt for a renderer script via a file dialog, then load it.

        Wired to the "Load" menu action (Ctrl+O). `getOpenFileName` returns a
        `(path, filter)` tuple; `path` is `''` if the dialog is cancelled, which
        `load_renderer` treats as "nothing to load" rather than an error.
        """
        rendererScriptName = qw.QFileDialog.getOpenFileName(self, 'Open File', './renderer',
                                                            "GLSL rendering script (*.py)", "",
                                                            qw.QFileDialog.DontUseNativeDialog)
        self.load_renderer(rendererScriptName[0])

    def reload(self):
        """Re-run `_load` against the currently loaded renderer path.

        Wired to the "Reload" menu action (Ctrl+R); unlike `load_renderer` this never
        accepts a new path, so it errors out if nothing has been loaded yet instead of
        silently no-oping.
        """
        if self._renderer_path:
            self._load()
        else:
            self._processHandler.error('Failed to reload: invalid renderer path')

    def importModuleFromPath(self):
        """Import `self._renderer_path` as a fresh module named `self.rendererName`.

        Registers the module in `sys.modules` under that name before executing it, so
        re-running this against the same path re-executes the file under a stable name
        -- the mechanism `_load`/`reload` rely on to hot-reload a renderer script
        without restarting the process. If execution raises, `self.imported` is left
        pointing at the new, only partially-run module object rather than the previous
        good one; the exception is caught and logged, not re-raised.
        """
        try:
            spec = util.spec_from_file_location(self.rendererName, location=self._renderer_path)
            self.imported = util.module_from_spec(spec)
            sys.modules[self.rendererName] = self.imported
            spec.loader.exec_module(self.imported)
        except:
            self._processHandler.error(traceback.format_exc())

    def restartDisplay(self):
        """Suspend the display process, then bring it back up with a freshly reloaded renderer.

        Busy-waits on `_displayProcName`'s `status` state after `suspendDisplay`
        succeeds: it repeatedly writes `1` until a read of that peer's status stops
        reporting `0`, i.e. until the display process has actually picked up the
        un-suspend, before calling `reload()` to send it a script. This blocks the
        calling (GUI) thread for as long as that round-trip takes. Wired to the
        "Restart Display" menu action (Ctrl+Shift+R).
        """
        suspended = self.suspendDisplay()
        if suspended == 0:
            while self._processHandler.get_state_from(self._displayProcName, 'status') == 0:
                self._processHandler.set_state_to(self._displayProcName, 'status', 1)
            self.reload()
            self._processHandler.info("Restarted [{}] core".format(self._displayProcName))
        else:
            self._processHandler.error(f'Unknown Error. Please retry to restart.')

    def suspendDisplay(self):
        """Ask the display process to suspend rendering and block until it confirms.

        Busy-waits, repeatedly writing `status = 0` until a read of `_displayProcName`'s
        status stops coming back positive, so a caller (`restartDisplay`, or the
        "Suspend Display" menu action) can rely on the peer having actually stopped by
        the time this returns. Returns 0 on success, -1 if the status exchange itself
        raises (e.g. the display process is not linked) -- `restartDisplay` uses that to
        decide whether it is safe to proceed.
        """
        try:
            while self._processHandler.get_state_from(self._displayProcName, 'status') > 0:
                self._processHandler.set_state_to(self._displayProcName, 'status', 0)
            self._processHandler.info("Suspended [{}] core".format(self._displayProcName))
            return 0
        except:
            self._processHandler.error(f'Failed to suspend [{self._displayProcName}] core')
            return -1

    def shutdown(self):
        """Signal the display process to terminate and block until it confirms.

        Busy-waits, repeatedly writing status -11 (the shutdown request code) until a
        read of `_displayProcName`'s status reports -1 (fully stopped) -- the same
        wait-for-peer pattern used by `suspendDisplay`/`restartDisplay`.
        """
        while self._processHandler.get_state_from(self._displayProcName, "status") != -1:
            self._processHandler.set_state_to(self._displayProcName, "status", -11)

class DataframeTable(qw.QTableView):
    """A QTableView that accepts a dropped spreadsheet file and loads it as its model."""

    def __init__(self, parent=None):
        """Enable drag-and-drop of files onto the table."""
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.filename = None

    def dragEnterEvent(self, event):
        """Qt drag-enter handler: accept the drag only if it carries URLs (i.e. dropped files)."""
        if event.mimeData().hasUrls:
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        """Qt drag-move handler: keep accepting the drag while it carries URLs."""
        if event.mimeData().hasUrls:
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        """Qt drop handler: load the dropped file if it is a URL pointing at an existing file.

        `urls()[0].path()` carries a leading "/" before the drive letter on Windows file
        URLs (e.g. "/C:/foo.xlsx"); the `[1:]` strips that so `os.path.isfile` sees a
        normal path.
        """
        if event.mimeData().hasUrls:
            url = event.mimeData().urls()[0].path()[1:]
            if os.path.isfile(url):
                self.loadfile(url)
                self.filename = url
        else:
            event.ignore()

    def loadfile(self, fdir):
        """Load `fdir` into the table if it is an Excel workbook.

        Silently does nothing for any other extension. `.h5` used to be accepted here
        and then handed to `pd.read_excel`, which cannot parse HDF5 -- a dropped `.h5`
        passed the extension check only to raise inside the reader. Supporting it for
        real would mean `pd.read_hdf` and a PyTables dependency this project does not
        declare, so the extension is simply no longer claimed.
        """
        if os.path.splitext(fdir)[1] in ['.xls', '.xlsx']:
            self.setModel(DataframeModel(data=pd.read_excel(fdir)))

class DataframeModel(qc.QAbstractTableModel):
    """A minimal read-only Qt table model wrapping a pandas DataFrame."""

    def __init__(self, data, parent=None):
        """Store `data` as the backing DataFrame for this model."""
        qc.QAbstractTableModel.__init__(self, parent)
        self._data = data

    def rowCount(self, parent=None):
        """Return the number of rows in the backing DataFrame."""
        return len(self._data.values)

    def columnCount(self, parent=None):
        """Return the number of columns in the backing DataFrame."""
        return self._data.columns.size

    def data(self, index, role=qc.Qt.DisplayRole):
        """Return the display string for the cell at `index`, or None for other roles/invalid indices."""
        if index.isValid():
            if role == qc.Qt.DisplayRole:
                # One positional lookup, not `.iloc[row][col]`. That form took a row as a
                # Series indexed by column *name* and then subscripted it with an int,
                # which worked only through the positional fallback pandas removed in 3.0
                # -- there it raises KeyError for every cell of a table whose columns are
                # strings, i.e. every protocol file.
                return str(self._data.iloc[index.row(), index.column()])
        return None

    def headerData(self, col, orientation, role):
        """Return the column name for horizontal display-role headers; otherwise None."""
        if orientation == qc.Qt.Horizontal and role == qc.Qt.DisplayRole:
            return self._data.columns[col]
        return None
