import os
import sys
sys.path.insert(1,os.getcwd())
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
    HOST = '192.168.1.103'  # Standard loopback interface address (localhost)
    PORT = 65432
    print(minion_manager.minions.keys())
    srv = mnp.simpleSocket('server',HOST,PORT)
    minion_manager.add_socket_connnection('display<->controller',srv)
    minion_manager.minions['display']._isrunning = False
    minion_manager.run(['display'])
