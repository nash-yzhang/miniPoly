import os
import sys
sys.path.insert(1,os.getcwd())
from Glimgui.GlImgui import glimWindow,glimManager
from glumpy import app
from pyfirmata import Arduino, util
import serial.tools.list_ports
from minipoly import miniPoly as mnp
from glumpy.app import clock
from time import time

def functest1(arduino_conn):
    # GIM = glimManager()
    config = app.configuration.Configuration()
    config.stencil_size = 8
    glimgui_win = glimWindow('glwin1',1024,720,config = config,minion_plug=arduino_conn)
    glimgui_win.import_sti_module('functest')
    glimgui_win.set_sti_module(essential_func_name= ['prepare','set_widgets'])
    # GIM.register_windows(glimgui_win)
    glimgui_win.run()
    sys.exit()
    # GIM.run()



def functest2(arduino_conn):
    # GIM = glimManager()
    config = app.configuration.Configuration()
    config.stencil_size = 8
    glimgui_win = glimWindow('glwin2',1024,720,config = config,minion_plug=arduino_conn)
    glimgui_win.import_sti_module('functest')
    glimgui_win.set_sti_module(essential_func_name= ['prepare','set_widgets'])
    # GIM.register_windows(glimgui_win)
    glimgui_win.run()
    sys.exit()
    # GIM.run()

if __name__ == '__main__' :
    minion_manager = mnp.manager()
    minion_manager.add_minion('glim', functest1)
    minion_manager.add_minion('arduino_IO', functest2)
    # minion_manager.add_queue_connection('glim<->arduino_IO')
    minion_manager.run('all')