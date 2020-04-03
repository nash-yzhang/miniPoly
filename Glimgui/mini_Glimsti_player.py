import os
import sys
sys.path.insert(1,os.getcwd())
from Glimgui.GlImgui import glimWindow,glimManager
from glumpy import app
import multiprocessing as mp
from minipoly import miniPoly as mnp
from glumpy.app import clock

def main(mi0):
    GIM = glimManager()
    config = app.configuration.Configuration()
    config.stencil_size = 8
    glimgui_win = glimWindow(1024,720,config = config,minion_plug=mi0)
    GIM.register_windows(glimgui_win)
    glimgui_win.set_sti_module('functest')
    GIM.run()


def print_fps(mi1):
    myclock = clock.Clock()
    myclock.set_fps_limit(1000)
    stayalive = True
    a = 0
    while stayalive:
        mi1.get(0, ['dt','isalive'])
        if 'dt' in mi1.inbox.keys():
            a = int(mi1.inbox['dt']*1000)
            print('mi0: %d, mi1: %d' %(a,int(myclock.tick()*1000)))
        if 'isalive' in mi1.inbox.keys():
            stayalive = mi1.inbox['isalive']



if __name__ == '__main__' :
    mi0 = mnp.minion(main,[])
    mi1 = mnp.minion(print_fps,[])
    prt,chd = mp.Pipe()
    mi0.add_target(chd)
    mi1.add_source(prt)
    mi0.Process.start()
    mi1.Process.start()
