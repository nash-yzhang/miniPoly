from bin import minion as mi
from time import sleep, time
from multiprocessing import Lock
import warnings
warnings.filterwarnings("ignore")

class Victim(mi.BaseMinion):
    def main(self):
        self.info(f'I am {self.name}, I am ALIVE!')
        sleep(0.1)


class Killer(mi.BaseMinion):
    def main(self):
        if (time() - self._elapsed) > .2:
            victums = [i for i in self._linked_minion.keys() if 'logger' not in i.lower()]
            alived = len(victums)
            for victim in victums:
                victim_status = self.get_state_from(victim, 'status')
                if not victim_status:
                    victim_status = 0
                if victim_status > 0:
                    self.warning(f'Killing {victim}...')
                    self.set_state_to(victim, 'status', -1)
                else:
                    alived -= 1
            if alived <= 0:
                self.shutdown()
            sleep(0.2)
        else:
            pass


if __name__ == '__main__':
    lock = Lock()
    v1 = Victim('Victim 1',lock)
    v2 = Victim('Victim 2',lock)
    k1 = Killer('Killer 1',lock)
    lm = mi.LoggerMinion('MAIN LOGGER',lock)
    v1.attach_logger(lm)
    v2.attach_logger(lm)
    k1.attach_logger(lm)
    v1.connect(k1)
    v2.connect(k1)
    lm.run()
    v1.run()
    v2.run()
    k1.run()
