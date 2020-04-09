# from minipoly.miniPoly import minion, manager
from Glimgui.GlImgui import glplayer
# import glfw

class glwin_server(glplayer):
    __windows__ = []
    __windows_to_remove__ = []
    __name__ = 'GlImgui_GLFW'

    def __init__(self):
        super().__init__()


    def register_glplayer(self,player_func):
        window._manager = self
        self.__windows__.append(window)
        self.add_minion(window.__name__,window.run)

    def execute(self):
        for window in self.__windows__:
            if isinstance(window, adapted_glumpy_window):
                if window._should_close:
                    self.__windows__.remove(window)
                    self.__windows_to_remove__.append(window)

        for window in self.__windows_to_remove__:
            window.close()
            window.destroy()
            self.__windows_to_remove__.remove(window)

    def run(self):
        while len(self.__windows__) + len(self.__windows_to_remove__) > 0:
            self.execute()
        sys.exit()