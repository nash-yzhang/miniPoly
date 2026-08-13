import copy
import logging
from datetime import datetime
from logging.handlers import QueueListener
from multiprocessing import Queue
from pathlib import Path
from queue import Empty
from time import monotonic, sleep

from miniPoly.core.minion import BaseMinion, MinionLogHandler, LOG_LVL_LOOKUP_TABLE


class ColorFormatter(logging.Formatter):
    """Formatter that wraps the level name, logger name and message in ANSI color codes.

    Colors by level so a console full of interleaved multi-process log lines
    stays scannable -- errors and warnings jump out without reading every line.
    """
    # Define color codes for different log levels
    COLORS = {
        'DEBUG': '\033[92m',    # Green
        'INFO': '\033[97m',     # Default color
        'WARNING': '\033[93m',  # Yellow
        'ERROR': '\033[91m',    # Red
        'CRITICAL': '\033[95m'  # Magenta
    }
    RESET = '\033[0m'  # Reset color

    def format(self, record):
        """Color the record's level name, logger name and message, then format normally.

        Mutates `record` in place before delegating to the base formatter, so the
        color codes end up embedded in the same fields a plain `Formatter` would
        substitute into its format string.
        """
        log_color = self.COLORS.get(record.levelname, self.RESET)
        record.levelname = f"{log_color}{record.levelname}{self.RESET}"
        record.name = f"{log_color}{record.name}{self.RESET}"
        record.msg = f"{log_color}{record.msg}{self.RESET}"
        return super().format(record)

class LoggerMinion(BaseMinion, QueueListener):
    """Centralized log sink: drains a multiprocess queue and dispatches to real handlers.

    Every other minion logs through a `MinionLogHandler` that puts records onto
    this minion's `multiprocessing.Queue`; `main()` dequeues them one at a time
    and hands them to the `logging` module's normal handler chain (console/file/
    error handlers from `DEFAULT_LISTENER_CONFIG`), which is the only place in
    the framework where those handlers actually run. It subclasses
    `QueueListener` for `dequeue`/`handle` but drives them itself from `main()`
    on the minion's own tick instead of `QueueListener`'s own background thread,
    since it must also watch its "reporters" (the minions it logs for) and shut
    itself down only once they are all gone -- it has to outlive every other
    minion, or their last messages are lost.
    """
    DEFAULT_LOGGER_CONFIG = {
        'version': 1,
        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
                'level': 'INFO'
            }
        },
        'root': {
            'handlers': ['console'],
            'level': 'DEBUG'
        }
    }

    #: Template for the listener configuration. The two `filename` entries below are
    #: placeholders and are **always** rewritten by `listener_config_for`, which is what
    #: builds the config actually used -- both because the directory is a decision the
    #: caller must make, and because the timestamp here is evaluated once at *class
    #: definition* time, i.e. at import. A long-lived interpreter that built two
    #: applications would otherwise have both write to the first one's filename, in
    #: `mode='w'`, and the second would silently truncate the first.
    DEFAULT_LISTENER_CONFIG = {
        'version': 1,
        'disable_existing_loggers': True,
        'respect_handler_level': True,
        'formatters': {
            'detailed': {
                # 'class': 'logging.Formatter',
                '()': ColorFormatter,
                'format': '%(asctime)-4s  %(name)-8s %(levelname)-8s %(processName)-10s %(message)s'
            },
            'simple': {
                # 'class': 'logging.Formatter',
                '()': ColorFormatter,
                'format': '%(asctime)-4s   %(levelname)-8s %(name)-8s   %(message)s'
            }
        },
        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
                'formatter': 'simple',
                'level': 'INFO'
            },
            'file': {
                'class': 'logging.FileHandler',
                'filename': f'logs/{datetime.now().strftime("%Y%m%d_%H%M%S")}.log',
                'mode': 'w',
                'formatter': 'detailed',
                'level': 'DEBUG'
            },
            'errors': {
                'class': 'logging.FileHandler',
                'filename': f'logs/ERROR_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log',
                'mode': 'w',
                'formatter': 'detailed',
                'level': 'ERROR'
            }
        },
        'root': {
            'handlers': ['console', 'file', 'errors'],
            'level': 'DEBUG'
        }
    }

    #: Seconds to sleep when the record queue is empty. Bounds both the logger's idle
    #: CPU cost and how long a record can sit unhandled.
    IDLE_POLL_INTERVAL = 0.001

    #: Seconds of quiet the final drain waits for before accepting that no more records
    #: are coming. Reset by every record received, so this is "nothing has arrived for
    #: this long", not a flat delay.
    #:
    #: It exists because `multiprocessing.Queue.empty()` cannot answer the question the
    #: drain is asking. `put()` does not write to the pipe; it appends to a buffer that a
    #: per-process **feeder thread** drains asynchronously, so a record can be logged,
    #: `put`, and still be invisible to the reader for some microseconds afterwards.
    #: `empty()` reports on what has arrived, never on what is coming -- and the records
    #: most likely to be in flight at shutdown are a minion's *last* ones, which are the
    #: ones worth having.
    DRAIN_GRACE = 0.25

    @classmethod
    def listener_config_for(cls, log_dir=None, name=None):
        """`DEFAULT_LISTENER_CONFIG` with its two files in `log_dir`, timestamped now.

        Creates the directory: `FileHandler` does not, and the logger is normally the
        first process to start, so a missing directory takes the whole launch down before
        anything useful has happened.

        The filename is ``<timestamp>_<name>.log``. Timestamp first so a directory listing
        sorts chronologically, which is what anyone reading a folder of these wants; the
        name after it because the timestamp alone is **not unique**. It has one-second
        resolution, and two applications sharing a `log_dir` -- the normal case now that
        the destination is stated rather than inherited from the working directory -- can
        start within the same second. Both handlers open in ``mode='w'``, so a collision
        is not two writers appending, it is one truncating the other. A `LoggerMinion` in
        an application built with ``[app] unique_names`` carries the launching PID in its
        name, which makes that impossible rather than merely unlikely.

        `log_dir=None` reproduces the historical behaviour -- a ``logs/`` resolved against
        the **process working directory**. That is a trap rather than a default: the
        destination is then whatever folder the application happened to be launched from,
        which is how 463 files totalling 1.3 GB once accumulated inside a source tree.
        Pass a real directory.
        """
        directory = Path('logs') if log_dir is None else Path(log_dir)
        directory.mkdir(parents=True, exist_ok=True)
        stem = datetime.now().strftime("%Y%m%d_%H%M%S")
        if name:
            stem = f"{stem}_{name}"
        # deepcopy, not dict(...): the two handlers to rewrite are nested two levels down,
        # and a shallow copy would mutate the class attribute itself. The formatters hold
        # a reference to the ColorFormatter *class*, which deepcopy treats as atomic.
        config = copy.deepcopy(cls.DEFAULT_LISTENER_CONFIG)
        config['handlers']['file']['filename'] = str(directory / f"{stem}.log")
        config['handlers']['errors']['filename'] = str(directory / f"ERROR_{stem}.log")
        return config

    def __init__(self, name, logger_config=None, listener_config=None, log_dir=None):
        """Set up the record queue and defer both logging configs to `main()`.

        `logger_config` is applied immediately (it configures logging in this,
        the parent, process before the child is forked); `listener_config` is
        stashed and only applied in `main()`, because `self.logger` itself must
        not be created until after `run()` has forked the child process -- a
        logger object created here would be carried into the child by pickling
        and then stop working there.

        `log_dir` is where the two log files go. It is the argument to reach for: passing
        it is the difference between stating a destination and inheriting whichever
        directory this process was started from. `listener_config` remains available for
        a caller that needs to replace the handler chain outright, and the two are
        mutually exclusive -- given both, `log_dir` would silently do nothing.
        """
        super(LoggerMinion, self).__init__(name=name)

        if listener_config is not None and log_dir is not None:
            raise ValueError(
                "LoggerMinion takes log_dir or listener_config, not both: a listener_config "
                "already names its own files, so log_dir would be ignored."
            )

        if logger_config is None:
            logger_config = self.DEFAULT_LOGGER_CONFIG
        if listener_config is None:
            # Also the only place that creates the log directory. It used to happen
            # unconditionally here, which meant a caller supplying its own listener_config
            # still got an empty `logs/` in the working directory it was trying to avoid.
            listener_config = self.listener_config_for(log_dir, name)

        logging.config.dictConfig(logger_config)
        self.logger = None
        # Start logger after run() as logger object won't pass the pickling core and will be switched off
        self.queue = Queue()
        self.handlers = [MinionLogHandler()]
        self.respect_handler_level = False
        self.listener_config = listener_config
        self.hasConfig = False
        self.reporter = []
        self._stopping = False

    def set_level(self, level):
        """Change the running logger's level and propagate it to all its handlers.

        Looks up `self.name`'s logger rather than `self.logger` directly so this
        is a no-op-safe call even before `main()` has created `self.logger` --
        `logging.getLogger` always returns (creating if needed) the same named
        logger instance.
        """
        level = level.upper()
        if level in LOG_LVL_LOOKUP_TABLE.keys():
            logLevel = LOG_LVL_LOOKUP_TABLE[level]
            logger = logging.getLogger(self.name)
            logger.setLevel(logLevel)
            for handler in logger.handlers:
                handler.setLevel(logLevel)
        else:
            self.warning(f"Unknown logging level: {level}")

    def register_reporter(self, reporter):
        """Link a minion to this logger and track it so `poll_reporter` can watch it.

        `connect` only queues the pair up for `build_init_conn` to actually link
        during startup; recording the name here (rather than the minion object)
        is what lets `poll_reporter` later query it purely by name through
        `is_minion_alive`.
        """
        self.connect(reporter)
        self.reporter.append(reporter.name)

    def poll_reporter(self):
        """Return whether every registered reporter now looks dead.

        Each reporter gets up to 3 lookups via `is_minion_alive`. A definite
        `True`/`False` settles it immediately; a reporter that only ever answers `None`
        -- it cannot be told, e.g. it is not linked yet -- counts as **alive**, because
        `main` shuts this minion down once every reporter reads dead, and the logger is
        meant to outlive the processes it logs for. Reading "cannot tell" as dead let a
        not-yet-linked reporter shut the logger down during startup, discarding exactly
        the errors it existed to record.

        The cost of that choice: this is `main`'s only self-shutdown trigger, so a
        reporter stuck permanently indeterminate -- registered under a name that never
        becomes linkable -- keeps the logger running instead of stopping it early. That
        case is loud rather than silent (`is_minion_alive` logs "is not connected" on
        every poll), which is why it is preferred over the reverse failure. A process
        that dies outright is not affected: its segment is gone, so the read raises
        FileNotFoundError and reports a definite False.
        """
        reporter_is_dead = [True] * len(self.reporter)
        for i, m in enumerate(self.reporter):
            err_counter = 0
            while err_counter < 3:
                is_alive = self.is_minion_alive(m)
                if is_alive is True:
                    reporter_is_dead[i] = False
                    break
                elif is_alive is False:
                    reporter_is_dead[i] = True
                    break
                elif is_alive is None:
                    err_counter += 1
            else:
                # Loop ran out without a definite answer: keep the reporter alive so
                # further error messages from it still have somewhere to go.
                reporter_is_dead[i] = False

        return all(reporter_is_dead)

    def main(self):
        """One tick: lazily finish setup, drain one queued record, and check for shutdown.

        The listener config and `self.logger` are both created here, on first
        call, rather than in `__init__` or `initialize()`, because they must
        exist only in the child process (see `__init__`). The queue is drained
        non-blocking rather than with `dequeue(True)` -- a blocking dequeue
        cannot observe reporter status while it waits, so once every reporter
        had gone quiet the logger used to stay parked in `dequeue` forever
        instead of shutting down last, as it is meant to (see B5 in the code
        comment below). When idle, a short sleep stands in for the pacing a
        blocking call would otherwise have provided, so an empty queue doesn't
        spin a whole CPU core.
        """
        if not self.hasConfig:
            logging.config.dictConfig(self.listener_config)
            self.hasConfig = True

        if self.logger is None:
            # self.logger starts only after the core has started
            self.logger = logging.getLogger(self.name)
            self.logger.setLevel(logging.INFO)
            self.info('----------------- START LOGGING -----------------')

        # Non-blocking. `dequeue(True)` blocks until a record arrives, and while blocked
        # it cannot observe the reporters' status -- so once the other minions went quiet
        # the logger was stuck in dequeue and never exited, even though it is started
        # last in VR_init.py and is supposed to exit last (B5).
        try:
            record = self.dequeue(False)
        except Empty:
            record = None

        if record is None:
            # innerLoop has no pacing of its own; blocking used to provide it. Without a
            # sleep an idle logger spins on an empty queue and burns a core.
            sleep(self.IDLE_POLL_INTERVAL)
        else:
            self.handle(record)

        if self.poll_reporter():
            self.shutdown()

    def shutdown(self):
        """Drain any remaining records, log the stop banner, and mark this minion terminated.

        Guarded to run only once (see the idempotency note below): `main()` can
        call this again before `innerLoop` notices `status` went negative and
        stops calling `main()`, since the status is only re-read every
        `STATUS_POLL_INTERVAL`.

        The drain waits for `DRAIN_GRACE` of quiet rather than for `queue.empty()`,
        because a reporter's final records are still crossing the queue's feeder thread
        at the moment its status reads dead. This is the whole reason the logger is
        started last and shuts down last -- draining early loses exactly the messages
        that say why a minion stopped.
        """
        # Idempotent. main() calls this as soon as poll_reporter() reports every reporter
        # gone, but innerLoop only re-reads the status every STATUS_POLL_INTERVAL, so main()
        # can run again -- and call this again -- before the loop notices and exits. That
        # window logged 'STOP LOGGING' twice and drained the queue twice.
        if self._stopping:
            return
        self._stopping = True
        deadline = monotonic() + self.DRAIN_GRACE
        while monotonic() < deadline:
            try:
                record = self.queue.get(timeout=self.IDLE_POLL_INTERVAL)
            except Empty:
                continue
            self.handle(record)
            # Something arrived, so something else may still be behind it. The wait is
            # for silence, not for a fixed interval.
            deadline = monotonic() + self.DRAIN_GRACE
        self.info('----------------- STOP LOGGING -----------------')
        self.set_state_to(self.name, "status", -1)
