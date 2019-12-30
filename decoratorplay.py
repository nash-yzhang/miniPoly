import multiprocessing as mp
import Decoration as dc
from IPython import embed
import time

def f(api):
    t = 1
    # a = 1

    # state = 1
    # api.put(locals(),'state')
    # while api.buffer_in['state']<1:
    #     api.get(0,'state')
    #     api.send(0,'state')

    while t<1000:
        api.put(locals(),'t')
        # while not api.buffer_in['t']:
        #     print(1)
        #     api.send(0,'t')
        #     api.get(0, 't')
        print('nf: %d' %t)
        api.send(0, 't')
        api.get(0, 't')
        if api.buffer_in['t']:
            if api.buffer_in['t']>t:
                t = api.buffer_in['t'] + 1

def printf(api):
    # state = 1
    # api.put(locals(),'state')
    # while not api.buffer_in:
    #     api.get(0,'state')
    # state = 2
    # api.put(locals(),'state')
    # api.send(0,'state')
    #
    # print("pf ready")
    while not api.buffer_in['t']:
        api.get(0, 't')

    while True:#api.src_chn[0].qsize()>0:
        t = api.buffer_in['t'] + 1
        print('Pf: %d' % t)
        api.put(locals(),'t')
        api.send(0, 't')
        if t >= 1000:
            print('over')
            break

        api.get(0, 't')

    # api.Process.terminate()
    # api.Process.join()


if __name__ == '__main__' :
    nf = dc.MPhandler(f, ['t', 'a'])
    pf = dc.MPhandler(printf,['t'])
    prt,chd = mp.Pipe()
    r_prt,r_chd = mp.Pipe()
    nf.add_target(chd)
    nf.add_source(r_prt)
    pf.add_target(r_chd)
    pf.add_source(prt)
    pf.Process.start()
    nf.Process.start()
    while nf.Process.is_alive():
        while pf.Process.is_alive():
            pass
        print("pf is dead")
    print("nf is dead")
#%%

# mp.Process()