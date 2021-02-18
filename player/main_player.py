import os
import sys
print(os.getcwd())
__rootpath__ = os.getcwd().replace('\\player','')
os.chdir(__rootpath__)
dll_path = __rootpath__ + '\\dll'
os.environ['PATH'] = dll_path + os.pathsep + os.environ['PATH']
sys.path.insert(0, __rootpath__)
from bin.GlImgui import glimWindow,glimListener
from glumpy import app
config = app.configuration.Configuration()
from bin import miniPoly as mnp

def functest_controller(hook):
    glimgui_win = glimWindow('main', 1024, 720, config=config,minion_plug=hook)
    glimgui_win.run()

if __name__ == '__main__' :
    minion_manager = mnp.manager()
    minion_manager.add_minion('main', functest_controller)
    minion_manager.run(['main'])
