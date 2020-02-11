import multiprocessing as mp
from IPython import embed
# noinspection SpellCheckingInspection

class Chunk (object) :
    _core = None
    def __init__(self, core_item, varname):
        self.varname = varname
        self._core = core_item
        self.tar_chn = []
        self.src_chn  = []
        self.buffer_in = {}
        self.buffer_out = {}
        for key in varname:
            self.buffer_in[key] = []
        self.Process = mp.Process(target=self._core, args=(self,))

    def add_source(self,source_channel):
        self.src_chn.append(source_channel)

    def add_target(self,target_channel):
        self.tar_chn.append(target_channel)

    def put(self, localvar, varname=None) :
        if not varname:
            varname = self.varname
        for key, value in localvar.items () :
            if not varname:
                self.buffer_out[key] = value
            else:
                if key in varname :
                    self.buffer_out[key] = value

    def send(self,chn_idx,varname = None):
        out_package = {}
        for key, value in self.buffer_out.items():
            if not varname:
                out_package[key] = value
            else:
                if key in varname:
                    out_package[key] = value

        chn = self.tar_chn[chn_idx]
        if isinstance(chn,type(mp.Queue())):
            chn.put(out_package)
        elif isinstance(chn,mp.connection.PipeConnection):
            chn.send(out_package)

    def get(self, chn_idx, varname=None) :
        chn = self.src_chn[chn_idx]
        if isinstance(chn, type(mp.Queue())):
            tin = self.src_chn[chn_idx].get()
        elif isinstance(chn, mp.connection.PipeConnection):
            tin = self.src_chn[chn_idx].recv()

        for key, value in tin.items():
            if varname:
                if key in varname:
                    self.buffer_in[key] = value
            else:
                self.buffer_in[key] = value