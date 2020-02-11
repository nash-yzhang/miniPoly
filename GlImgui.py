import copy
import glfw
import imgui
from imgui.integrations.glfw import GlfwRenderer
from glumpy import app, gloo, gl, glm
from glumpy.log import log
from glumpy.app import configuration,parser,clock
from glumpy.app.window.backends import backend_glfw
import sys, os
from importlib import import_module

class glimWindow(backend_glfw.Window):
    _backend = app.use('glfw')
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

        super().__init__(*args, **kwargs)
        config = configuration.gl_get_configuration()
        self._config = config
        self._clock = clock.get_default()

        log.info("Using %s (%s %d.%d)" %
                 ('glfw', config.api,
                  config.major_version, config.minor_version))

        if config.samples > 0:
            log.info("Using multisampling with %d samples" %
                     (config.samples))

        # Display fps options
        if options.display_fps:
            @self.timer(1.0)
            def timer(elapsed):
                print("Estimated FPS: %f"% self._clock.get_fps())

        self._native_window.__class__ = self.GLFW_WIN_CLASS
        self._init_width = copy.copy(self.width)
        self._init_height = copy.copy(self.height)
        imgui.create_context()
        self.imgui_renderer = GlfwRenderer(self._native_window)
        self.open_dialog_state = False
        self.sti_file_dir = "<Stimulu file directory>"
        self.selected = False
        self.fn_idx = 0
        self.event_func_list = ['prepare','set_imgui_widgets','on_draw','on_init']

        self.register_event_type("prepare")
        self.register_event_type("set_imgui_widgets")

    def prepare(self):
        pass
    def set_imgui_widgets(self):
        pass

    # def update_method(self,filename):


    def start(self):
        self.dispatch_event("prepare")
        while not glfw.window_should_close(self._native_window):
            self.clear()
            glfw.poll_events()
            self.imgui_renderer.process_inputs()
            imgui.new_frame()

            if imgui.begin_main_menu_bar():
                if imgui.begin_menu("File", True):
                    self.open_dialog_state,_ = imgui.menu_item("Open..","",False,True)
                    clicked_quit, _ = imgui.menu_item(
                        "Quit", 'Cmd+Q', False, True
                    )
                    if clicked_quit:
                        break
                    imgui.end_menu()
                imgui.end_main_menu_bar()
            if self.open_dialog_state:
                imgui.set_next_window_size(400,400)
                imgui.open_popup("Select file")
                if imgui.begin_popup_modal("Select file")[0]:
                    _, self.sti_file_dir = imgui.input_text(' ',self.sti_file_dir,256)
                    if os.path.isdir(self.sti_file_dir):
                        file_list = [file for file in os.listdir(self.sti_file_dir) if file.endswith(".py")]
                    else:
                        file_list = []
                    _,self.fn_idx = imgui.combo(
                        "", self.fn_idx, file_list
                    )
                    if imgui.button("Select"):
                        sys.path.insert(0, self.sti_file_dir)
                        self.selected = True
                        self.import_pkg = import_module(file_list[self.fn_idx].split('.')[0])
                        self.open_dialog_state = False

                    imgui.same_line()
                    if imgui.button("Cancel"):
                        self.open_dialog_state = False
                    imgui.end_popup()

            if self.selected:
                print(11111111)
                for func in self.event_func_list:
                    if func in self.import_pkg.__dict__:
                        getattr(self.import_pkg,func).__globals__['self'] = self
                        self.event(getattr(self.import_pkg,func))
                self.dispatch_event('prepare')
                self.selected = False
            #         self.event(locals()[func])

            self.dispatch_event("set_imgui_widgets")

            imgui.render()
            self.imgui_renderer.render(imgui.get_draw_data())
            glfw.swap_buffers(self._native_window)


        self.imgui_renderer.shutdown()
        self.close()
        glfw.terminate()

    def _update_event(self,func_name):
        if self.imported_pkg:
            self.event(getattr(self.imported_pkg,func_name))

    def close(self):
        print("close")
        glfw.destroy_window(self._native_window)