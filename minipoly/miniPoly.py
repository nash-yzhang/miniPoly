import multiprocessing as mp
# from IPython import embed
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

    def put(self, var_pkg, varname) :
        if type(var_pkg) == dict:
            put_var = {k:var_pkg[k] for k in varname}
        else:
            put_var = {k:getattr(var_pkg,k) for k in varname}
        self.outbox.update(put_var)

    def give(self, chn_idx, varname):
        out_package = {k:self.outbox[k] for k in varname}
        chn = self._giveto[chn_idx]
        if isinstance(chn,type(mp.Queue())):
            chn.put(out_package)
        elif isinstance(chn,mp.connection.PipeConnection):
            chn.send(out_package)

    def get(self, chn_idx, varname) :
        chn = self._getfrom[chn_idx]
        if chn.poll():
            if isinstance(chn, type(mp.Queue())):
                in_package = self._getfrom[chn_idx].get()
            elif isinstance(chn, mp.connection.PipeConnection):
                in_package = self._getfrom[chn_idx].recv()

            self.inbox.update({k:in_package[k] for k in set(in_package.keys())&set(varname)})