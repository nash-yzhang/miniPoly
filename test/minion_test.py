from bin import minion as mi
from time import sleep,time

class Victim(mi.BaseMinion):
    def main(self):
        print(f'I am {self.name}, I am ALIVE!')
        sleep(0.2)

class Killer(mi.BaseMinion):
    def main(self):
        alived = len(self._linked_minion.keys())
        for victim in self._linked_minion.keys():
            victim_status = self.get_state_from(victim,'status')
            if victim_status > 0:
                print(f'Killing {victim}...')
                self.set_state_to(victim,'status',-2)
            else:
                alived -= 1
        if alived <= 0:
            self.shutdown()
        sleep(0.01)

if __name__ == '__main__':
    v1 = Victim('Victim 1')
    v2 = Victim('Victim 2')
    k1 = Killer('Killer 1')
    v1.connect(k1)
    v2.connect(k1)
    v1.run()
    v2.run()
    sleep(3)
    k1.run()
