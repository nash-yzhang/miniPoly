from Glimgui.GlImgui import glimWindow,glimManager
from glumpy import app

GIM = glimManager()
config = app.configuration.Configuration()
config.stencil_size = 8
glimgui_win = glimWindow(1024,720,config = config)
GIM.register_windows(glimgui_win)
glimgui_win.set_sti_module('muti_ICcam')
# glimgui_win.set_sti_module('multicamp')


GIM.run()

