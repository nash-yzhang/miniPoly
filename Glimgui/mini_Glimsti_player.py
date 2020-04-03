import os
import sys
sys.path.insert(1,os.getcwd())
from Glimgui.GlImgui import glimWindow,glimManager
from glumpy import app
from minipoly import miniPoly as pc

def main(connector):
    GIM = glimManager()
    config = app.configuration.Configuration()
    config.stencil_size = 8
    glimgui_win = glimWindow(1024,720,config = config)
    GIM.register_windows(glimgui_win)
    glimgui_win.set_sti_module('functest')
    GIM.run()

if __name__ == '__main__' :
    nf = pc.minion(main,[])
    nf.Process.start()
