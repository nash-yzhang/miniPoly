import multiprocessing as mp
import socket, pickle
import sys
from time import time,sleep

class Manager(mp.managers.SyncManager) :
    def __init__(self):
        self._queues = {}
        super(Manager, self).__init__()

    def register(self,minion):
        self._minions[minion._name] = minion
        return self


    def request_queue(self,src_name,tgt_name):
        if_src_exist = src_name in self._minions.keys()
        if_tgt_exist = tgt_name in self._minions.keys()
        if if_src_exist and if_tgt_exist:
            self._queues['{} to {}'.format(src_name,tgt_name)] = []
            q = self.Queue()
            self._queues['{} to {}'.format(src_name,tgt_name)].append(q)
            self._minions[tgt_name].add_target(src_name,q)
            return q
        else:
            if not if_src_exist:
                print("Source not found: {}".format(src_name))
            if not if_tgt_exist:
                print("Target not found: {}".format(tgt_name))


def task_wrapper(hook):
    while hook._isalive:
        if hook._isrunning:
            hook.put({'isrunning':True})
            hook.give('all',['isrunning'])
            hook._func(hook)
            if "restart" in hook._name:
                hook._isrunning = True
                hook._name = "_".join(hook._name.split("_")[:-1])
                print("Restarting "+hook._name)
            else:
                hook._isrunning = False
                print(hook._name+" is off")
            hook.put({'isrunning': False})
            hook.give('all', ['isrunning'])
            if "shutdown" in hook._name:
                hook._isalive = False
        else:
            hook.comm()
            sleep(0.01)
    hook.shutdown()

class Minion (object) :
    _func = None
    def __init__(self, manager:Manager, name, main_func):
        self._manager = manager
        self._name = name
        self._func = main_func
        self._regVar = {} # the rpc-modifiable variable name must be registered
        self._stack = []  # a dictionary of output channels storing rpc function name-value pair (marshalled) E.g.: {'receiver_minion_1':('terminate',True)}
        self._queue  = {} # a dictionary of inbox for receiving rpc calls
        self.Process = mp.Process(target=task_wrapper, args=(self,))

    def add_source(self, src_name):
        source_channel = self._manager.request_queue(src_name,self._name)
        self._queue[src_name] = source_channel

    def add_target(self,target_minion_name,target_channel):
        self._stack[target_minion_name] = target_channel

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

    def give(self, minion_name, varname):
        out_pkg = {k:self.outbox[k] for k in varname}
        if minion_name == 'all':
            for chn in self._stack.values():
                self._give(chn,out_pkg)
        else:
            self._give(self._stack[minion_name], out_pkg)

    def _get(self,chn):
        if isinstance(chn, type(mp.Queue())):
            if not chn.empty():
                in_package = chn.get()
                self.inbox.update(in_package)
        elif isinstance(chn, mp.connection.PipeConnection):
            if chn.poll():
                in_package = chn.recv()
                self.inbox.update(in_package)

    def get(self, minion_name) :
        if minion_name == 'all':
            for chn in self._queue.values():
                self._get(chn)
        else:
            self._get(self._queue[minion_name])

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
        if target in self._stack:
            self.put({"should_live": False})
            self.give(target, ['should_live'])
            if target in self._manager.minions.keys():
                self._manager.minions.pop(target)
        else:
             print(f"{bcolors.bRED}ERROR: {bcolors.YELLOW}Target [{bcolors.bRESET}%s{bcolors.YELLOW}] not found" % target)


# class manager (object):
#     def __init__(self):
#         self.minions = {}
#         self.pipes = {}
#         self.queue = {}
#         self.socket_conn = {}
#
#     def add_minion(self, minion_name, task_method,**kwargs):
#         if minion_name not in self.minions.keys():
#             self.minions[minion_name] = minion(minion_name,task_method,**kwargs)
#             self.minions[minion_name]._manager = self
#         else:
#             print(f"{bcolors.bRED}ERROR: {bcolors.YELLOW}Name [{bcolors.bRESET}%s{bcolors.YELLOW}] already taken"%minion_name)
#
#     def add_pipe_connection(self,conn_exp_str):
#         if "->" in conn_exp_str:
#             if "<->" in conn_exp_str:
#                 [sn,tn] = conn_exp_str.split("<->")
#                 r_src, r_tar = mp.Pipe()
#                 self.minions[sn].add_source(tn,r_src)
#                 self.minions[tn].add_target(sn,r_tar)
#             else:
#                 [sn,tn] = conn_exp_str.split("->")
#             src, tar = mp.Pipe()
#             self.minions[sn].add_target(tn,tar)
#             self.minions[tn].add_source(sn,src)
#
#     def add_queue_connection(self,conn_exp_str,queue_size = 1):
#         if "->" in conn_exp_str:
#             if "<->" in conn_exp_str:
#                 [sn,tn] = conn_exp_str.split("<->")
#                 self.queue[sn+'<-'+tn] = mp.Queue(queue_size)
#                 self.minions[sn].add_source(tn,self.queue[sn+'<-'+tn])
#                 self.minions[tn].add_target(sn,self.queue[sn+'<-'+tn])
#             else:
#                 [sn,tn] = conn_exp_str.split("->")
#             self.queue[sn + '->' + tn] = mp.Queue(queue_size)
#             self.minions[sn].add_target(tn, self.queue[sn + '->' + tn])
#             self.minions[tn].add_source(sn, self.queue[sn + '->' + tn])
#
#     def add_socket_connnection(self,conn_exp_str,skt):
#         if "->" in conn_exp_str:
#             if "<->" in conn_exp_str:
#                 [sn,tn] = conn_exp_str.split("<->")
#                 if skt.skt_type == "server":
#                     self.minions[sn].add_source(tn,skt)
#                     self.minions[sn].add_target(tn,skt)
#                 elif skt.skt_type == "client":
#                     self.minions[tn].add_source(sn,skt)
#                     self.minions[tn].add_target(sn,skt)
#             else:
#                 [sn,tn] = conn_exp_str.split("->")
#                 if skt.skt_type == "server":
#                     self.minions[sn].add_target(tn, skt)
#                 elif skt.skt_type == "client":
#                     self.minions[tn].add_source(sn, skt)
#
#
#     def run(self,minion_name):
#         if minion_name == "all":
#             for mini in self.minions.values():
#                 mini.Process.start()
#         else:
#             for mini in minion_name:
#                 self.minions[mini].Process.start()

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
