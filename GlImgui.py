import copy
import glfw
import imgui
from imgui.integrations.glfw import GlfwRenderer
from glumpy import app, gloo, gl, glm
from glumpy.log import log
from glumpy.app import configuration,parser,clock
from glumpy.app.window.backends import backend_glfw
import sys, os
from importlib import import_module,reload
import numpy as np

class glimWindow(backend_glfw.Window):
    _backend = app.use('glfw')
    glfw.init()
    fakewindow = glfw.create_window(10, 10, "None", None, None)
    GLFW_WIN_CLASS = fakewindow.__class__
    glfw.destroy_window(fakewindow)

    def __init__(self,*args,**kwargs):
        options = parser.get_options()
        config = configuration.get_default()
        if "config" not in kwargs.keys():
            kwargs['config'] = config
        if 'vsync' not in kwargs.keys():
            kwargs['vsync'] = options.vsync
        imgui.create_context()
        self.imgui_context = imgui.get_current_context()
        imgui.set_current_context(self.imgui_context)
        super().__init__(*args, **kwargs)
        config = configuration.gl_get_configuration()
        self._config = config
        self._clock = clock.Clock()

        log.info("Using %s (%s %d.%d)" %
                 ('glfw', config.api,
                  config.major_version, config.minor_version))

        if config.samples > 0:
            log.info("Using multisampling with %d samples" %
                     config.samples)

        # Display fps options
        if options.display_fps:
            @self.timer(1.0)
            def timer(elapsed):
                print("Estimated FPS: %f"% self._clock.get_fps())
        self._manager = None
        self._shouldClose = False
        self._native_window.__class__ = self.GLFW_WIN_CLASS
        self._init_width = copy.copy(self.width)
        self._init_height = copy.copy(self.height)
        self._texture_buffer = np.zeros((self.height, self.width, 4), np.float32).view(gloo.TextureFloat2D)
        self._depth_buffer = gloo.DepthBuffer(self.width, self.height)
        self._framebuffer = gloo.FrameBuffer(color=[self._texture_buffer], depth=self._depth_buffer)
        self.dt = 1e-10

        self.imgui_renderer = GlfwRenderer(self._native_window)
        self.io = imgui.get_io()
        self.open_dialog_state = False
        self.should_quit = False
        self.sti_file_dir = "..."
        self.selected = False
        self.fn_idx = 0
        self.event_func_list = ['prepare','set_imgui_widgets','on_draw','on_init','on_resize']
        # self.import_pkg = None

        self.register_event_type("prepare")
        self.register_event_type("set_imgui_widgets")

    def prepare(self):
        pass

    def on_resize(self,width, height):
        return None

    def set_sti_module(self,sti_module_name):
        if hasattr(self, 'import_pkg'):
            if sti_module_name == self.import_pkg.__name__:
                self.import_pkg = reload(self.import_pkg)
            else:
                self.import_pkg = import_module(sti_module_name)
        else:
            self.import_pkg = import_module(sti_module_name)

        for func in self.event_func_list:
            if func in self.import_pkg.__dict__:
                getattr(self.import_pkg, func).__globals__['self'] = self
                self.event(getattr(self.import_pkg, func))
        self.dispatch_event('prepare')

    def set_imgui_widgets(self):
        pass
    
    def set_basic_widgets(self):
        if imgui.begin_main_menu_bar():
            if imgui.begin_menu("File", True):
                self.open_dialog_state, _ = imgui.menu_item("Open..", "", False, True)
                self.should_quit, _ = imgui.menu_item(
                    "Quit", 'Cmd+Q', False, True
                )
                imgui.end_menu()
            imgui.end_main_menu_bar()
        if self.open_dialog_state:
            imgui.set_next_window_size(400, 400)
            imgui.open_popup("Select file")
            if imgui.begin_popup_modal("Select file")[0]:
                _, self.sti_file_dir = imgui.input_text(' ', self.sti_file_dir, 256)
                if os.path.isdir(self.sti_file_dir):
                    file_list = [file for file in os.listdir(self.sti_file_dir) if file.endswith(".py")]
                else:
                    file_list = []
                _, self.fn_idx = imgui.combo(
                    "", self.fn_idx, file_list
                )
                if imgui.button("Select"):
                    sys.path.insert(0, self.sti_file_dir)
                    self.set_sti_module((file_list[self.fn_idx].split('.')[0]))
                    self.open_dialog_state = False

                imgui.same_line()
                if imgui.button("Cancel"):
                    self.open_dialog_state = False
                imgui.end_popup()

    def process(self):
        # self.dispatch_event("prepare")
        # while not glfw.window_should_close(self._native_window):
        self.dt = self._clock.tick()
        self.clear()
            # glfw.poll_events()
        self.imgui_renderer.process_inputs()
        imgui.new_frame()
        self.set_basic_widgets()
        self.dispatch_event("set_imgui_widgets")
        imgui.render()
        self.imgui_renderer.render(imgui.get_draw_data())
            # self.swap()
            # glfw.swap_buffers(self._native_window)
            # if self.should_quit:
            #     break
        # self.imgui_renderer.shutdown()
        # glfw.destroy_window(self._native_window)
        # glfw.terminate()
        # self.close()

    def close(self):
        self.imgui_renderer.shutdown()
        glfw.set_window_should_close(self._native_window, True)


class glimManager:
    __windows__ = []
    __windows_to_remove__ = []
    __name__ = 'GlImgui_GLFW'

    def __init__(self):
        glfw.init()

    def register_windows(self,glimWin:glimWindow):
        # assert isinstance(glimWin, glimWindow)
        glimWin._manager = self
        # glimWin.dispatch_event("prepare")
        self.__windows__.append(glimWin)

    def execute(self):
        glfw.poll_events()
        # TODO: FINALIZE HERE to make it behave like app.run
        for window in self.__windows__:
            if isinstance(window,glimWindow):
                if glfw.window_should_close(window._native_window):
                    self.__windows__.remove(window)
                    self.__windows_to_remove__.append(window)
                else:
                    window.activate()
                    # imgui.set_current_context(window.imgui_context)
                    # imgui.set
                    window.process()
            else:
                window._native_window.__class__ = glimWindow.GLFW_WIN_CLASS
                if glfw.window_should_close(window._native_window):
                    self.__windows__.remove(window)
                    self.__windows_to_remove__.append(window)
                else:
                    window.activate()
                    window.dispatch_event('on_draw', clock.tick())
                    window.dispatch_event('on_idle', clock.tick())
            window.swap()

        for window in self.__windows_to_remove__:
            window.destroy()
            self.__windows_to_remove__.remove(window)


    def run(self):

        while len(self.__windows__)+len(self.__windows_to_remove__)>0:
            self.execute()
        sys.exit()




