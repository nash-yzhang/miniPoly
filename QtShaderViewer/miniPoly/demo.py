import time as ti
from QtShaderViewer.miniPoly.core import Minion

class minionA(Minion):
    def main(self):
        for tgt in self.target.keys():
            self.send(tgt, 'Greetings from {}\n'.format(self.name))
        for key in self.source.keys():
            msg = self.get(key)
            if msg:
                print('[{}]:{}\n'.format(key,msg))
                if "Killing" in msg:
                    for tgt in self.target.keys():
                        self.set_state(tgt,"status",-1)
                    self.shutdown()
        ti.sleep(.1)

class minionB(Minion):
    def main(self):
        ti.sleep(.2)
        for tgt in self.target.keys():
            self.send(tgt, 'Killing {}\n'.format(tgt))
        for key in self.source.keys():
            msg = self.get(key)
            if msg:
                print('[{}]:{}'.format(key, msg))
            # ti.sleep(1)


if __name__ == "__main__":
    m1 = minionA('ma')
    m2 = minionB('mb')
    m1.add_target(m2)
    m2.add_target(m1)
    m2.run()
    m1.run()