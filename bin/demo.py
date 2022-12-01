from time import sleep
from minion import BaseMinion,LoggerMinion
import logging

class baseMinionA(BaseMinion):
    def main(self):
        for tgt in self._conn.keys():
            self.log(logging.INFO,"Send greeting message to {}".format(tgt))
            self.send(tgt, 'Greetings from {}\n'.format(self.name))

        for key in self._conn.keys():
            msg = self.get(key)
            if msg:
                self.log(logging.INFO,"[{}]:{}".format(tgt,msg))
                if "Killing" in msg:
                    for tgt in self._conn.keys():
                        self.set_state(tgt,"status",-1)
                    self.shutdown()
        sleep(.01)

class baseMinionB(BaseMinion):
    def main(self):
        for tgt in self._conn.keys():
            self.send(tgt, 'Killing {}\n'.format(tgt))
        for key in self._conn.keys():
            msg = self.get(key)
            if msg:
                self.log(logging.INFO,"[{}]:{}".format(key,msg))
        sleep(.01)

if __name__ == "__main__":
    lm = LoggerMinion()
    m1 = baseMinionA('m1')
    m2 = baseMinionB('m2')
    m1.attach_logger(lm)
    m2.attach_logger(lm)
    m1.add_connection(m2)
    m2.add_connection(m1)
    m1.run()
    m2.run()
    lm.run()
    # lm.stop_event.set()
