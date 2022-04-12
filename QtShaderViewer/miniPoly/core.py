import multiprocessing as mp
from multiprocessing import Value, Queue
from multiprocessing.managers import SyncManager
from time import time, sleep




class Minion:
    @staticmethod
    def innerLoop(hook):
        STATE = hook.get_state(hook.name,"status")
        while STATE>=0:
            if STATE == 1:
                hook.main()
            elif STATE == 0:
                print(hook.name + " is suspended")
                sleep(0.01)
            STATE = hook.get_state(hook.name,"status")
            # print(STATE)
        hook.shutdown()
        print(hook.name + " is off")

    def __init__(self, name):
        self.name = name
        self.source = {}  # a dictionary of output channels storing rpc function name-value pair (marshalled) E.g.: {'receiver_minion_1':('terminate',True)}
        self.target = {}  # a dictionary of inbox for receiving rpc calls
        self.state = {'{}_{}'.format(self.name, 'status'):Value('i', 0)}
        self.sharedBuffer = {}  # a dictionary of inbox for receiving rpc calls

    def add_source(self, src):
        self.share_state_handle(src.name, "status", src.get_state_handle(src.name, "status"))
        self.source[src.name] = src.target[self.name]

    def add_target(self, tgt):
        self.share_state_handle(tgt.name, "status", tgt.get_state_handle(tgt.name, "status"))
        self.target[tgt.name] = Queue()
        tgt.add_source(self)

    def send(self, tgt_name, val):
        if self.get_state(tgt_name,"status") > 0:
            chn = self.target[tgt_name]
            if not chn.full():
                chn.put(val)
            else:
                print(" Send failed: the queue for '{}' is fulled".format(tgt_name))
        else:
            print("Send failed: '{}' has been terminated".format(tgt_name))

    def get(self, src_name):
        chn = self.source[src_name]
        if self.get_state(src_name,"status") > 0:
            if not chn.empty():
                received = chn.get()
            else:
                print("[{}] Empty Queue".format(src_name))
                received = None
        else:
            print("Receive failed: '{}' has been terminated".format(src_name))
            received = None
        return received

    def add_buffer(self, buffer_name, buffer_handle):
        self.sharedBuffer[buffer_name] = buffer_handle

    def get_state(self, minion_name, category):
        return self.state['{}_{}'.format(minion_name, category)].value

    def get_state_handle(self, minion_name, category):
        return self.state['{}_{}'.format(minion_name, category)]

    def set_state(self, minion_name, category, value):
        self.state['{}_{}'.format(minion_name, category)].value = value

    def share_state_handle(self, minion_name, category, value):
        self.state.update({'{}_{}'.format(minion_name, category): value})

    def run(self):
        self.Process = mp.Process(target=Minion.innerLoop, args=(self,))
        self.set_state(self.name,"status",1)
        self.Process.start()

    def main(self):
        pass

    def shutdown(self):
        self.set_state(self.name,"status",-1)
        if self.Process._popen:
            self.Process.terminate()
            self.Process.close()