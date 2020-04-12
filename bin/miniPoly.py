import multiprocessing as mp
import socket, pickle
# from IPython import embed
# noinspection SpellCheckingInspection

class minion (object) :
    _task = None
    def __init__(self, name, task_method):
        self._name = name
        self._task = task_method
        self._giveto = {}
        self._getfrom  = {}
        self.inbox = {}
        self.outbox = {}
        self.Process = mp.Process(target=self._task, args=(self,))

    def add_source(self,source_minion_name,source_channel):
        self._getfrom[source_minion_name] = source_channel
        # self._getfrom.append(source_channel)

    def add_target(self,target_minion_name,target_channel):
        self._giveto[target_minion_name] = target_channel

    def put(self, var_pkg, varname) :
        if type(var_pkg) == dict:
            put_var = {k:var_pkg[k] for k in varname}
        else:
            put_var = {k:getattr(var_pkg,k) for k in varname}
        self.outbox.update(put_var)

    def give(self, minion_name, varname):
        out_package = {k:self.outbox[k] for k in varname}
        chn = self._giveto[minion_name]
        if isinstance(chn,type(mp.Queue())):
            if not chn.full():
                chn.put(out_package)
        elif isinstance(chn,mp.connection.PipeConnection):
            chn.send(out_package)
        elif isinstance(chn, simpleSocket):
            datastring = pickle.dumps(out_package)
            chn.send(datastring)

    def get(self, minion_name, varname) :
        chn = self._getfrom[minion_name]
        if isinstance(chn, type(mp.Queue())):
            if not chn.empty():
                in_package = self._getfrom[minion_name].get()
                self.inbox.update({k: in_package[k] for k in set(in_package.keys()) & set(varname)})
        elif isinstance(chn, mp.connection.PipeConnection):
            if chn.poll():
                in_package = self._getfrom[minion_name].recv()
                self.inbox.update({k:in_package[k] for k in set(in_package.keys())&set(varname)})
        elif isinstance(chn, simpleSocket):
            data = chn.recv(4096)
            if data:
                in_package = pickle.loads(data)
                self.inbox.update({k: in_package[k] for k in set(in_package.keys()) & set(varname)})


class manager (object):
    def __init__(self):
        self.minions = {}
        self.pipes = {}
        self.queue = {}
        self.socket_conn = {}

    def add_minion(self, minion_name, task_method):
        if minion_name not in self.minions.keys():
            self.minions[minion_name] = minion(minion_name,task_method)
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
