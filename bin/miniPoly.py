import multiprocessing as mp
import socket, pickle
import sys
from time import time,sleep

# noinspection SpellCheckingInspection

def task_wrapper(hook):
    while hook._isalive:
        if hook._isrunning:
            hook.put({'isrunning':True})
            hook.give('all',['isrunning'])
            hook._task(hook)
            hook._isrunning = False
            print(hook._name+" is off")
            hook.put({'isrunning': False})
            hook.give('all', ['isrunning'])
            if hook._name == 'main':
                hook._isalive = False
        else:
            hook.comm()
            sleep(0.01)
    hook.shutdown()

class minion (object) :
    _task = None
    def __init__(self, name, task_method, custom_var = {}):
        self._manager = 'unknown'
        self._name = name
        self._task = task_method
        self._giveto = {}
        self._getfrom  = {}
        self._pocket = custom_var
        self.inbox = {}
        self.outbox = {}
        self._isalive = True
        self._isrunning = True
        self._timeout = None
        self.Process = mp.Process(target=task_wrapper, args=(self,))

    def add_source(self,source_minion_name,source_channel):
        self._getfrom[source_minion_name] = source_channel

    def add_target(self,target_minion_name,target_channel):
        self._giveto[target_minion_name] = target_channel

    def get_pocket(self,varname):
        return self._pocket[varname]

    def put(self, var_pkg, varname = '') :
        if type(var_pkg) == dict:
            if varname:
                put_var = {k:var_pkg[k] for k in varname}
            else:
                put_var = var_pkg
        else:
            put_var = {k:getattr(var_pkg,k) for k in varname}
        self.outbox.update(put_var)

    def _give(self,chn,out_pkg):
        if isinstance(chn,type(mp.Queue())):
            if not chn.full():
                chn.put(out_pkg)
        elif isinstance(chn,mp.connection.PipeConnection):
            chn.send(out_pkg)
        elif isinstance(chn, simpleSocket):
            datastring = pickle.dumps(out_pkg)
            chn.send(datastring)

    def give(self, minion_name, varname):
        out_pkg = {k:self.outbox[k] for k in varname}
        if minion_name == 'all':
            for chn in self._giveto.values():
                self._give(chn,out_pkg)
        else:
            self._give(self._giveto[minion_name],out_pkg)

    def _get(self,chn):
        if isinstance(chn, type(mp.Queue())):
            if not chn.empty():
                in_package = chn.get()
                self.inbox.update(in_package)
        elif isinstance(chn, mp.connection.PipeConnection):
            if chn.poll():
                in_package = chn.recv()
                self.inbox.update(in_package)
        elif isinstance(chn, simpleSocket):
            data = chn.recv(4096)
            if data:
                in_package = pickle.loads(data)
                # self.inbox.update({k: in_package[k] for k in set(in_package.keys()) & set(varname)})
                self.inbox.update(in_package)

    def get(self, minion_name) :
        if minion_name == 'all':
            for chn in self._getfrom.values():
                self._get(chn)
        else:
            self._get(self._getfrom[minion_name])

    def fetch(self,var_to_get):
        if type(var_to_get) == list:
            return {x: self.inbox[x] if x in self.inbox.keys() else None for x in var_to_get}
        elif type(var_to_get) == dict:#var_dict = {inbox varname: local varname}
            return {value:self.inbox[key] for key, value in var_to_get.items() if key in self.inbox.keys()}

    def pop(self,var_to_get):
        if type(var_to_get) == list:
            return {x: self.inbox.pop(x) if x in self.inbox.keys() else None for x in var_to_get}
        elif type(var_to_get) == dict:#var_dict = {inbox varname: local varname}
            return {value:self.inbox.pop(key) for key, value in var_to_get.items() if key in self.inbox.keys()}

    def comm(self):
        self.get("all")
        self.__dict__.update(self.pop({"should_run":"_isrunning"}))
        self.__dict__.update(self.fetch({"should_live":"_isalive"}))
        if not self._isalive:
            self._isrunning = False
            self.shutdown(1)

    def shutdown(self,timeout = 0):
        if not self._timeout:
            self._timeout = time()
        timepass = time()-self._timeout
        self.put({'isalive': False})
        self.give('all', ['isalive'])
        if self.Process._popen:
            self.Process.terminate()
            self.Process.close()

    def remote_shutdown(self,target):
        if target in self._giveto:
            self.put({"should_live": False})
            self.give(target, ['should_live'])
            if target in self._manager.minions.keys():
                self._manager.minions.pop(target)
        else:
             print(f"{bcolors.bRED}ERROR: {bcolors.YELLOW}Target [{bcolors.bRESET}%s{bcolors.YELLOW}] not found" % target)


class manager (object):
    def __init__(self):
        self.minions = {}
        self.pipes = {}
        self.queue = {}
        self.socket_conn = {}

    def add_minion(self, minion_name, task_method,**kwargs):
        if minion_name not in self.minions.keys():
            self.minions[minion_name] = minion(minion_name,task_method,**kwargs)
            self.minions[minion_name]._manager = self
        else:
            print(f"{bcolors.bRED}ERROR: {bcolors.YELLOW}Name [{bcolors.bRESET}%s{bcolors.YELLOW}] already taken"%minion_name)

    def add_pipe_connection(self,conn_exp_str):
        if "->" in conn_exp_str:
            if "<->" in conn_exp_str:
                [sn,tn] = conn_exp_str.split("<->")
                r_src, r_tar = mp.Pipe()
                self.minions[sn].add_source(tn,r_src)
                self.minions[tn].add_target(sn,r_tar)
            else:
                [sn,tn] = conn_exp_str.split("->")
            src, tar = mp.Pipe()
            self.minions[sn].add_target(tn,tar)
            self.minions[tn].add_source(sn,src)

    def add_queue_connection(self,conn_exp_str,queue_size = 1):
        if "->" in conn_exp_str:
            if "<->" in conn_exp_str:
                [sn,tn] = conn_exp_str.split("<->")
                self.queue[sn+'<-'+tn] = mp.Queue(queue_size)
                self.minions[sn].add_source(tn,self.queue[sn+'<-'+tn])
                self.minions[tn].add_target(sn,self.queue[sn+'<-'+tn])
            else:
                [sn,tn] = conn_exp_str.split("->")
            self.queue[sn + '->' + tn] = mp.Queue(queue_size)
            self.minions[sn].add_target(tn, self.queue[sn + '->' + tn])
            self.minions[tn].add_source(sn, self.queue[sn + '->' + tn])

    def add_socket_connnection(self,conn_exp_str,skt):
        if "->" in conn_exp_str:
            if "<->" in conn_exp_str:
                [sn,tn] = conn_exp_str.split("<->")
                if skt.skt_type == "server":
                    self.minions[sn].add_source(tn,skt)
                    self.minions[sn].add_target(tn,skt)
                elif skt.skt_type == "client":
                    self.minions[tn].add_source(sn,skt)
                    self.minions[tn].add_target(sn,skt)
            else:
                [sn,tn] = conn_exp_str.split("->")
                if skt.skt_type == "server":
                    self.minions[sn].add_target(tn, skt)
                elif skt.skt_type == "client":
                    self.minions[tn].add_source(sn, skt)


    def run(self,minion_name):
        if minion_name == "all":
            for mini in self.minions.values():
                mini.Process.start()
        else:
            for mini in minion_name:
                self.minions[mini].Process.start()

class simpleSocket:
    def __init__(self,skt_type,host, port):
        self.program = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.skt_type = skt_type
        if skt_type == "server":
            self.program.bind((host, port))
            self.program.listen()
            self.conn, self.addr = self.program.accept()
        elif skt_type == "client":
            self.program.connect((host, port))

    def send(self,*args,**kwargs):
        if self.skt_type == "server":
            self.conn.send(*args,**kwargs)
        elif self.skt_type == "client":
            self.program.send(*args, **kwargs)

    def recv(self,*args,**kwargs):
        if self.skt_type == "server":
            return self.conn.recv(*args,**kwargs)
        elif self.skt_type == "client":
            return self.program.recv(*args, **kwargs)
        # if self.skt_type == "server":
        #     self.conn.recv(*args,**kwargs)
        # elif self.skt_type == "client":
        #     self.program.recv(*args, **kwargs)


class bcolors:
    RED     = '\033[31m'
    YELLOW  = '\033[33m'
    CYAN = '\033[36m'
    RESET   = '\033[0m'

    bRED    = '\033[1;31m'
    bYELLOW = '\033[1;33m'
    bCYAN = '\033[1;36m'
    bRESET   = '\033[1;0m'

    uRED    = '\033[4;31m'
    uYELLOW = '\033[4;33m'
    uCYAN = '\033[4;36m'
    uRESET   = '\033[4;0m'
