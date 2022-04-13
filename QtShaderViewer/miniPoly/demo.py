import time as ti
from core import BaseMinion,LoggerMinion
import logging

class baseMinionA(BaseMinion):
    def main(self):
        self.log(logging.INFO,"Send greeting message...")
        # for tgt in self.target.keys():
            # self.send(tgt, 'Greetings from {}\n'.format(self.name))

        # for key in self.source.keys():
            # msg = self.get(key)
            # if msg:
            #     # print('[{}]:{}\n'.format(key,msg))
            #     if "Killing" in msg:
            #         for tgt in self.target.keys():
            #             self.set_state(tgt,"status",-1)
            #         self.shutdown()
        ti.sleep(.2)
        self.shutdown()

class baseMinionB(BaseMinion):
    def main(self):
        ti.sleep(2e-5)
        for tgt in self.target.keys():
            self.send(tgt, 'Killing {}\n'.format(tgt))
        for key in self.source.keys():
            msg = self.get(key)
            if msg:
                print('[{}]:{}'.format(key, msg))
            # ti.sleep(1)


if __name__ == "__main__":
    lm = LoggerMinion()
    m1 = baseMinionA('m1')
    m2 = baseMinionA('m2')
    m1.attach_logger(lm)
    m2.attach_logger(lm)
    m1.run()
    m2.run()
    lm.run()
    # lm.stop_event.set()