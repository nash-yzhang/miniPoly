import multiprocessing as mp
from time import perf_counter

class streamer:

    def __init__(self, process_name: str, _ctrlQueue: mp.Queue=None, _logQueue: mp.Queue = None, _inPipe = None):
        self._name = process_name
        self._ctrlQueue = _ctrlQueue
        self._logQueue = _logQueue
        self._inPipe = _inPipe
        self._buffer = []
        self._status = 0

    def _sendToProcess(self, process, data):
        """
        Convenience function to send messages to other Processes.
        All messages have the format [Sender, Receiver, Data]
        :param process:
        :param data:
        :return: None
        """
        self._ctrlQueue.put([self._name, process.name, data])

    @property
    def Status(self):
        return self._status

    @Status.setter
    def Status(self,status):
        self._status = status

    def Main(self):
        pass

    def run(self):
        self.Status = 1

        # Run event loop
        self.t = perf_counter()
        while self.Status > -1:
            if self.Status != 0:
                self._handlePipe()
                self.main()
                self.t = perf_counter()

