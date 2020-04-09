import os
import sys
sys.path.insert(1,os.getcwd())
from Glimgui.GlImgui import glimWindow,glplayer
from glumpy import app
config = app.configuration.Configuration()
from minipoly import miniPoly as mnp

def functest_controller(hook):
    glimgui_win = glimWindow('controller', 1024, 720, config=config,minion_plug=hook)
    glimgui_win.import_sti_module('Glimgui.functest_controller')
    glimgui_win.set_sti_module()
    glimgui_win.run()
    sys.exit()

def functest_display(hook):
    glimgui_win = glplayer('display', 1024, 720, config=config,minion_plug=hook)
    glimgui_win.import_sti_module('Glimgui.functest_display')
    glimgui_win.set_sti_module()
    glimgui_win.run()
    sys.exit()

if __name__ == '__main__' :
    minion_manager = mnp.manager()
    minion_manager.add_minion('controller', functest_controller)
    minion_manager.add_minion('display', functest_display)
    HOST = '127.0.0.1'  # Standard loopback interface address (localhost)
    PORT = 65432
    srv = mnp.simpleSocket('server',HOST,PORT)
    # minion_manager.add_queue_connection('controller->display')
    minion_manager.add_socket_connnection('controller->display',srv)
    minion_manager.run(['controller'])
