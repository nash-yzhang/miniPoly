from GlImgui import glimWindow,glimManager
from importlib import import_module
GIM = glimManager()
glimgui_win = glimWindow(1024,720)
GIM.register_windows(glimgui_win)
glimgui_win.set_sti_module('functest')


GIM.run()
