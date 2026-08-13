"""The smallest complete miniPoly rig: two processes, no central manager.

Run it with `uv run python examples/two_minions.py`. The sensor ticks every
millisecond and publishes one state; the follower reads that state by name and takes
the rig down once it crosses a threshold. Nothing registers anything anywhere.

The wiring at the bottom is written out by hand, deliberately: this file exists to show
what a rig *is*, and every line of it is a decision you would otherwise have to take on
trust. Once those four steps are familiar, stop writing them -- `examples/two_minions_
config.py` builds this same rig from a TOML file through `miniPoly.launcher`, which is
how a real application should be assembled.
"""

from miniPoly.compiler.prototypes import AbstractCompiler
from miniPoly.processor.prototypes import AbstractAPP
from miniPoly.processor.Logging import LoggerMinion


class Sensor(AbstractCompiler):
    """Owns one state. Nothing else in the rig had to be told it exists."""

    def __init__(self, processHandler):
        super().__init__(processHandler)
        self.create_state('reading', 0.0)
        self._n = 0

    def on_time(self, t):
        self._n += 1
        self.set_state('reading', self._n * 0.5)


class Follower(AbstractCompiler):
    """Reads a peer's state by name -- no registry, no message type, no schema."""

    def __init__(self, processHandler):
        super().__init__(processHandler)
        self._done = False

    def on_time(self, t):
        # `shutdown()` *requests* a stop; it does not return out of the tick loop. The
        # loop re-reads this minion's status only every STATUS_POLL_INTERVAL, so on_time
        # is still called a few more times afterwards -- and by then SENSOR is gone, so
        # each of those reads would log 'Dead minion'. One flag is the whole fix.
        if self._done:
            return
        reading = self.get_state_from('SENSOR', 'reading')
        # None means "not published yet": the peer declares its states inside its own
        # process, so a reader can be ready first.
        if reading is not None and reading >= 50:
            self.info(f'reading reached {reading}; taking the rig down')
            self.set_state_to('SENSOR', 'status', -1)
            self._done = True
            self.shutdown()


if __name__ == '__main__':
    # Construct, connect, attach, run -- the same four steps in the same order for every
    # rig ever built on miniPoly, which is why `miniPoly.launcher.Application` now does
    # them for you. They are spelled out here once so you can see what it does.
    logger = LoggerMinion('LOGGER', log_dir='logs')

    # The compiler *class* is passed in, not an instance: it is constructed inside the
    # child process, which is what lets Qt / vispy / ctypes objects live in a minion at
    # all under Windows spawn.
    sensor = AbstractAPP('SENSOR', Sensor, refresh_interval=1)      # 1 ms tick
    follower = AbstractAPP('FOLLOWER', Follower, refresh_interval=1)

    follower.connect(sensor)                                       # who may read whom
    for minion in (sensor, follower):
        minion.attach_logger(logger)

    logger.run()
    sensor.run()
    follower.run()
