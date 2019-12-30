import multiprocessing as mp
from Decoration import Bugger
from IPython import embed
import time

def f(api):
    t = 0
    a = 1
    api.append(locals(),'a')
    while t<1000:
        t = t+1
        api.append(locals(),'t')

def printf(q):
    while q.qsize()>0:
        print(q.get())

def get_f(f):
    return f()

def main():
    nf = Bugger(['t','a'],f)
    pf = mp.Process(target = printf, args=(nf.varbuffer,))
    nf.Process.start ()
    pf.start()
    while nf.Process.is_alive () :
        pass
    else :
        nf.Process.terminate ()
        nf.Process.join ()

    while pf.is_alive () :
        pass
    else :
        pf.terminate ()
        pf.join ()

    # while not nf.varbuffer.empty():
    #     pass
    # nf.Process.kill()
    # pf.join()


if __name__ == '__main__' :
    main()
#%%

# mp.Process()