import multiprocessing as mp
from minipoly import miniPoly as mnpl
from glumpy.app import clock

def f(api):
    myclock = clock.Clock()
    myclock.set_fps_limit(50)
    print(1)

    while True:#api.src_chn[0].qsize()>0:
        t = int(myclock.tick() * 1000)
        api.get(0, 't')
        api.put(locals(), 't')
        api.give(0, 't')
        if 't' in api.inbox.keys():
            another_t = int(api.inbox['t'])
            print('Pf: %d' % t)
            print('mi0: %d, mi1: %d' % (t,another_t))
        if t >= 1000:
            print('over')
            break
    # while t<1000:
    #     api.put(locals(),'t')
    #     # while not api.buffer_in['t']:
    #     #     print(1)
    #     #     api.send(0,'t')
    #     #     api.get(0, 't')
    #     print('nf: %d' %t)
    #     api.give(0, 't')
    #     api.get(0, 't')
    #     if api.inbox['t']:
    #         if api.inbox['t']>t:
    #             t = api.inbox['t'] + 1

def printf(api):
    myclock2 = clock.Clock()
    myclock2.set_fps_limit(100)
    # state = 1
    # api.put(locals(),'state')
    # while not api.buffer_in:
    #     api.get(0,'state')
    # state = 2
    # api.put(locals(),'state')
    # api.send(0,'state')
    #
    # print("pf ready")

    while True:#api.src_chn[0].qsize()>0:
        t = int(myclock2.tick() * 1000)
        api.get(0, 't')
        api.put(locals(), 't')
        api.give(0, 't')
        if 't' in api.inbox.keys():
            another_t = int(api.inbox['t'])
            print('mi0: %d, mi1: %d' % (another_t, t))
        if t >= 1000:
            print('over')
            break



    # api.Process.terminate()
    # api.Process.join()


if __name__ == '__main__' :
    nf = mnpl.minion(f, [])
    pf = mnpl.minion(printf, [])
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
