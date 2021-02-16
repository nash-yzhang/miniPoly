from bin.miniPoly import minion,manager
from time import sleep
import sys

def task1(hook):
    print(1)
    # hook._isrunning = False

def task2(hook):
    print(2)

def task_control(hook):
    print(3)
    # sleep(3)
    # outpkg = {'isrunning':True}
    # hook.put(outpkg,['isrunning'])
    # hook.give('reporter',['isrunning'])


if __name__ == '__main__' :
    minion_manager = manager()
    minion_manager.add_minion('controller',task_method=task1)
    minion_manager.add_minion('reporter', task_method=task2)
    minion_manager.add_queue_connection("controller<->reporter")
    minion_manager.run(["reporter"])