import multiprocessing as mp
from IPython import embed
# noinspection SpellCheckingInspection

class minion (object) :
    _task = None
    def __init__(self, task_method, varname):
        self.varname = varname
        self._task = task_method
        self._giveto = []
        self._getfrom  = []
        self.inbox = {}
        self.outbox = {}
        for key in varname:
            self.inbox[key] = []
        self.Process = mp.Process(target=self._task, args=(self,))

    def add_source(self,source_channel):
        self._getfrom.append(source_channel)

    def add_target(self,target_channel):
        self._giveto.append(target_channel)

    def put(self, localvar, varname=None) :
        if not varname:
            varname = self.varname
        for key, value in localvar.items () :
            if not varname:
                self.outbox[key] = value
            else:
                if key in varname :
                    self.outbox[key] = value

    def give(self, chn_idx, varname = None):
        out_package = {}
        for key, value in self.outbox.items():
            if not varname:
                out_package[key] = value
            else:
                if key in varname:
                    out_package[key] = value

        chn = self._giveto[chn_idx]
        if isinstance(chn,type(mp.Queue())):
            chn.put(out_package)
        elif isinstance(chn,mp.connection.PipeConnection):
            chn.send(out_package)

    def get(self, chn_idx, varname=None) :
        chn = self._getfrom[chn_idx]
        if isinstance(chn, type(mp.Queue())):
            tin = self._getfrom[chn_idx].get()
        elif isinstance(chn, mp.connection.PipeConnection):
            tin = self._getfrom[chn_idx].recv()

        for key, value in tin.items():
            if varname:
                if key in varname:
                    self.inbox[key] = value
            else:
                self.inbox[key] = value