<<<<<<< Updated upstream:player/mini_player.py
import os
import sys
sys.path.insert(0,os.getcwd())
from bin.GlImgui import glimWindow,glplayer
from glumpy import app
import bin.miniPoly as mnp
from time import sleep

def functest1(hook):
#     # GIM = glimManager()
    config = app.configuration.Configuration()
    config.stencil_size = 8
    glimgui_win = glimWindow(hook._name,1024,720,config = config,minion_plug=hook)
    glimgui_win.import_sti_module('stimulus.CMN2D')
    glimgui_win.set_sti_module(essential_func_name= ['prepare','set_widgets'], draw_func_name = None)
    glimgui_win.run()
    hook._isalive = False

if __name__ == '__main__' :
    minion_manager = mnp.manager()
    minion_manager.add_minion('glim', functest1)
=======
import os,sys
__rootpath__ = 'C:\\Users\\yzhang\\Desktop\\miniPoly-v0.3'
os.chdir(__rootpath__)
dll_path = __rootpath__+'\\dll'
os.environ['PATH'] = dll_path + os.pathsep + os.environ['PATH']
sys.path.insert(0,__rootpath__)
from bin.GlImgui import glimWindow,glplayer
from glumpy import app
import bin.miniPoly as mnp
from time import sleep

def functest1(hook):
#     # GIM = glimManager()
    config = app.configuration.Configuration()
    glimgui_win = glimWindow(hook._name,1024,720,config = config,minion_plug=hook)
    # glimgui_win.import_sti_module('stimulus.CMN2D')
    # glimgui_win.set_sti_module(essential_func_name= ['prepare','set_widgets'], draw_func_name = None)
    glimgui_win.run()
    hook._isalive = False

if __name__ == '__main__' :
    minion_manager = mnp.manager()
    minion_manager.add_minion('glim', functest1)
>>>>>>> Stashed changes:bin/before 20200511/mini_player.py
    minion_manager.run('all')