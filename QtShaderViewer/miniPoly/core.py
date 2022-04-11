import multiprocessing as mp
from multiprocessing import Value,Queue
from multiprocessing.managers import BaseManager
from time import time,sleep

class Manager(BaseManager) :
    def __init__(self):
        self._queues = {}
        self._minions = {}
        self._minionShutter = {}
        super(Manager, self).__init__()

    def register(self,minion):
        self._minions[minion._name] = minion
        self._minionShutter[minion._name] = minion._stateHandle
        return self

    def request_queue(self,src_name,tgt_name):
        if_src_exist = src_name in self._minions.keys()
        if_tgt_exist = tgt_name in self._minions.keys()
        if if_src_exist and if_tgt_exist:
            self._queues['{} to {}'.format(src_name,tgt_name)] = []
            q = Queue()
            self._queues['{} to {}'.format(src_name,tgt_name)].append(q)
            self._minions[tgt_name].add_source(src_name,q)
            print("{} to {} connected".format(src_name,tgt_name))
            return q
        else:
            if not if_src_exist:
                print("Source not found: {}".format(src_name))
            if not if_tgt_exist:
                print("Target not found: {}".format(tgt_name))


class Minion (object) :
    @staticmethod
    def innerLoop(hook):
        while hook.state>=0:
            if hook.state == 1:
                hook._func(hook)
            elif hook.state == 2:
                hook.state = 1
                print("Restarting " + hook._name)
            elif hook.state == 0:
                print(hook._name + " is suspended")
                sleep(0.01)
        print("Shutting down" + hook._name)
        hook.shutdown()
        print(hook._name + "is off")

    def __init__(self, manager:Manager, name, func):
    # def __init__(self, name, func):
        self._name = name
        self._manager = manager
        self._func = func
        self._stateHandle = Value('i',0)
        self.state = self._stateHandle.value
        self._regVar = {} # the rpc-modifiable variable name must be registered
        self._stack = {}  # a dictionary of output channels storing rpc function name-value pair (marshalled) E.g.: {'receiver_minion_1':('terminate',True)}
        self._queue  = {} # a dictionary of inbox for receiving rpc calls
        self.source = []
        self.target = []
        self.Process = mp.Process(target=Minion.innerLoop, args=(self,))
        # SHUTTER[self._name] = self._stateHandle
        self._manager.register(self)



    def add_source(self, src_name, chn):
        self._queue[src_name] = chn
        self.source.append(src_name)

    def add_target(self,tgt_name):
        chn = self._manager.request_queue(self._name,tgt_name)
        self._stack[tgt_name] = chn
        self.target.append(tgt_name)

    def check_state(self,minion_name):
        return self._minionShutter[minion_name].value
        # return SHUTTER[minion_name].value

    def send(self,tgt_name,val):
        if self.check_state(tgt_name)>0:
            chn = self._stack[tgt_name]
            if not chn.full():
                chn.put(val)
            else:
                print(" Send failed: the queue for '{}' is fulled".format(tgt_name))
        else:
            print("Send failed: '{}' has been terminated".format(tgt_name))

    def receive(self,src_name):
        chn = self._queue[src_name]
        if self.check_state(src_name) > 0:
            if not chn.empty():
                received = chn.get()
            else:
                print("[{}] Empty Queue".format(src_name))
                received = None
        else:
            print("Receive failed: '{}' has been terminated".format(src_name))
        return received

    def run(self):
        self.state = 1
        self._minionShutter = self._manager._minionShutter
        self._manager = None
        self.Process.start()

    # def put(self, var_pkg, varname = '') :
    #     '''
    #     :param var_pkg: an object or dictionary
    #     :param varname:
    #     :return:
    #     '''
    #     if type(var_pkg) == dict:
    #         if varname:
    #             put_var = {k:var_pkg[k] for k in varname}
    #         else:
    #             put_var = var_pkg
    #     else:
    #         put_var = {k:getattr(var_pkg,k) for k in varname}
    #     self.outbox.update(put_var)
    #
    # def _give(self,chn,out_pkg):
    #     if isinstance(chn,type(mp.Queue())):
    #         if not chn.full():
    #             chn.put(out_pkg)
    #
    # def give(self, minion_name, varname):
    #     out_pkg = {k:self.outbox[k] for k in varname}
    #     if minion_name == 'all':
    #         for chn in self._stack.values():
    #             self._give(chn,out_pkg)
    #     else:
    #         self._give(self._stack[minion_name], out_pkg)
    #
    # def _get(self,chn):
    #     if isinstance(chn, type(mp.Queue())):
    #         if not chn.empty():
    #             in_package = chn.get()
    #             self.inbox.update(in_package)
    #     elif isinstance(chn, mp.connection.PipeConnection):
    #         if chn.poll():
    #             in_package = chn.recv()
    #             self.inbox.update(in_package)
    #
    # def get(self, minion_name) :
    #     if minion_name == 'all':
    #         for chn in self._queue.values():
    #             self._get(chn)
    #     else:
    #         self._get(self._queue[minion_name])
    #
    # def fetch(self,var_to_get):
    #     if type(var_to_get) == list:
    #         return {x: self.inbox[x] if x in self.inbox.keys() else None for x in var_to_get}
    #     elif type(var_to_get) == dict:#var_dict = {inbox varname: local varname}
    #         return {value:self.inbox[key] for key, value in var_to_get.items() if key in self.inbox.keys()}
    #
    # def pop(self,var_to_get):
    #     if type(var_to_get) == list:
    #         return {x: self.inbox.pop(x) if x in self.inbox.keys() else None for x in var_to_get}
    #     elif type(var_to_get) == dict:#var_dict = {inbox varname: local varname}
    #         return {value:self.inbox.pop(key) for key, value in var_to_get.items() if key in self.inbox.keys()}
    #
    # def comm(self):
    #     self.get("all")
    #     self.__dict__.update(self.pop({"should_run":"_isrunning"}))
    #     self.__dict__.update(self.fetch({"should_live":"_isalive"}))
    #     if not self._isalive:
    #         self._isrunning = False
    #         self.shutdown(1)

    def shutdown(self,timeout = 0):
        self.state = -1
        if self.Process._popen:
            self.Process.terminate()
            self.Process.close()

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
