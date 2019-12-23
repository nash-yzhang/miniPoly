import multiprocessing as mp
from queue import Queue
from Decoration import Bugger


@Bugger(['t','a'])
def f(api):
    t = 0
    a = 1
    while t<1000:
        t = t+1
        print(t)
        api.append(locals())


def printf(q):
    while q.qsize()>0:
        print(q.get())

def get_f(f):
    return f()
# f.__module__ = "__main__"

q = Queue()
q.put('Start Now')
p1 = mp.Process(target = get_f, args = (f,))
# p2 = mp.Process(target = printf, args = (q,))
p1.start()
# p2.start()
p1.join()
# p2.join()
#%%

# mp.Process()