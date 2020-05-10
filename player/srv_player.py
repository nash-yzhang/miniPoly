import os
import sys
sys.path.insert(0,os.getcwd())
from bin.GlImgui import glimWindow,glimListener
from glumpy import app
config = app.configuration.Configuration()
from bin import miniPoly as mnp

def functest_controller(hook):
    glimgui_win = glimWindow('controller', 1024, 720, config=config,minion_plug=hook)
    glimgui_win.run()

def functest_display(hook):
    glimgui_win = glimListener(hook)
    glimgui_win.run()

if __name__ == '__main__' :
    minion_manager = mnp.manager()
    minion_manager.add_minion('controller', functest_controller)
    minion_manager.add_minion('display', functest_display)
    minion_manager.run(['controller'])
