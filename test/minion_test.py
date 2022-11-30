from bin import minion as mi
from time import sleep,time

class Victim(mi.BaseMinion):
    def main(self):
        print(f'I am {self.name}, I am ALIVE [{self.status}]!')
        sleep(0.5)

class Killer(mi.BaseMinion):
    def main(self):
        if (time()-self._elapsed) > 3:
            victums = [i for i in self._linked_minion.keys()]
            alived = len(victums)
            for victim in victums:
                victim_status = self.get_state_from(victim,'status')
                if not victim_status:
                    victim_status = 0
                if victim_status > 0:
                    print(f'Killing {victim}...')
                    self.set_state_to(victim,'status',-2)
                else:
                    alived -= 1
            if alived <= 0:
                self.shutdown()
            sleep(0.01)
        else:
            pass

if __name__ == '__main__':
    v1 = Victim('Victim 1')
    v2 = Victim('Victim 2')
    k1 = Killer('Killer 1')
    v1.connect(k1)
    v2.connect(k1)
    v1.run()
    v2.run()
    k1.run()
    1
