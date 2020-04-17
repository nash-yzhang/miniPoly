import copy
import glfw
import imgui
from imgui.integrations.glfw import GlfwRenderer
from glumpy import app, gloo, gl, glm
from glumpy.log import log
from glumpy.app import configuration, parser, clock
from glumpy.app.window.backends import backend_glfw
import sys, os
from importlib import import_module, reload
from inspect import getmembers, isfunction
import numpy as np
from PIL import Image as pimg

class magic_hat:
    def __init__(self,**kwargs):
        self.__dict__.update(kwargs)

    def add(self,**kwargs):
        self.__dict__.update(kwargs)

class adapted_glumpy_window(backend_glfw.Window):
    _backend = app.use('glfw')
    glfw.init()
    fakewindow = glfw.create_window(10, 10, "None", None, None)
    GLFW_WIN_CLASS = fakewindow.__class__
    glfw.destroy_window(fakewindow)
    _internal_VS = """
    attribute vec2 position;
    attribute vec2 texcoord;
    varying vec2 v_texcoord;
    void main()
    {
        gl_Position = vec4(position,0.0,1.0);
        v_texcoord = texcoord;
    }
    """
    _internal_FS = """
    uniform sampler2D texture;
    varying vec2 v_texcoord;
    void main()
    {
        gl_FragColor = texture2D(texture, v_texcoord);
    }
    """
    _internal_draw_program = gloo.Program(_internal_VS, _internal_FS, count=4)
    _internal_draw_program["position"] = np.array([(+1., +1.), (+1., -1.), (-1., +1.), (-1., -1.)])
    _internal_draw_program['texcoord'] = np.array([(1., 1.), (1., 0.), (0., 1.), (0., 0.)])

    def __init__(self, win_name, *args, **kwargs):
        self._name = win_name
        options = parser.get_options()
        config = configuration.get_default()
        if "config" not in kwargs.keys():
            kwargs['config'] = config
        if 'vsync' not in kwargs.keys():
            kwargs['vsync'] = options.vsync

        # self.imgui_context = imgui.get_current_context()
        # imgui.set_current_context(self.imgui_context)
        super().__init__(*args, **kwargs)
        self._init_config = config
        config = configuration.gl_get_configuration()
        self._config = config
        self._clock = clock.Clock()
        self._should_close = False

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
                print("Estimated FPS: %f" % self._clock.get_fps())
        self._manager = None
        self._native_window.__class__ = self.GLFW_WIN_CLASS
        self._init_width = copy.copy(self.width)
        self._init_height = copy.copy(self.height)
        self.dt = 1e-10

    def process(self):
        self.dt = self._clock.tick()
        self.clear()
        self.dispatch_event("on_draw", self.dt)

    def run(self):
        while True:
            glfw.poll_events()
            if self._should_close:
                break
            else:
                self.activate()
                self.process()
                self.swap()

    def close(self):
        self._should_close = True
        glfw.set_window_should_close(self._native_window, True)

class glplayer(adapted_glumpy_window):
    def __init__(self, *args, **kwargs):
        if 'minion_plug' in kwargs.keys():
            self.minion_plug = kwargs.pop('minion_plug')
            self._name = self.minion_plug._name
            if self.minion_plug._manager == 'unknown':
                self.minion_manager = None
            else:
                self.minion_manager = self.minion_plug._manager
        else:
            self.minion_plug = None

        super().__init__(*args, **kwargs)
        self._parent = None

    def import_sti_module(self,sti_module_name):
        if hasattr(self, 'import_stipgm'):
            if sti_module_name == self.import_stipgm.__name__:
                self.import_stipgm = reload(self.import_stipgm)
            else:
                self.import_stipgm = import_module(sti_module_name)
        else:
            self.import_stipgm = import_module(sti_module_name)

    def set_sti_module(self, essential_func_name = [], draw_func_name = "draw_main"):
        # Event dispatcher initialization
        import_func_list = [o for o in getmembers(self.import_stipgm) if isfunction(o[1])]
        self.event_func_list = [o[0] for o in import_func_list if o[1].__module__ == self.import_stipgm.__name__]
        if draw_func_name:
            assert (draw_func_name != 'on_draw'), ('\033[31mDraw function name cannot be the same as the buitin function \'on_draw\'')
            self._draw_func_name = draw_func_name
            essential_func_name.append(draw_func_name)
        assert all(func in self.event_func_list for func in essential_func_name), ('\033[31m' + 'the following functions is not defined in the imported module: %s' % (', '.join(func for func in essential_func_name if func not in self.event_func_list)))

        glumpy_default_func_list = ['on_init', 'on_draw', 'on_resize']

        for func in self.event_func_list:
            getattr(self.import_stipgm, func).__globals__['self'] = self
            self.event(getattr(self.import_stipgm, func))
            if func not in glumpy_default_func_list:
                self.register_event_type(func)
            # else
            #     if func == self._draw_func_name:
            #         self._draw_func_name = 'custom_'+self._draw_func_name
            # else:
            #     self._event_stack[0][func] = getattr(self.import_stipgm, func)

        self.dispatch_event('prepare')

    # def on_resize(self, width, height):
    #     # self.dispatch_event('on_resize',width,height)
    #     return None

    def process(self):
        self.dt = self._clock.tick()
        self.clear()
        self.dispatch_event(self._draw_func_name)

    def close(self):
        self._should_close = True
        if "terminate" in self.event_func_list:
            self.dispatch_event("terminate")
        glfw.set_window_should_close(self._native_window, True)
        self.destroy()

class glimWindow(glplayer):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        glfw.set_window_icon(self._native_window, 1, pimg.open('MappApp.ico'))

        self._texture_buffer = np.zeros((self.height, self.width, 4), np.float32).view(gloo.Texture2D)
        self._depth_buffer = gloo.DepthBuffer(self.width, self.height)
        self._framebuffer = gloo.FrameBuffer(color=[self._texture_buffer], depth=self._depth_buffer)

        # Imgui param init
        imgui.create_context()
        self.imgui_renderer = GlfwRenderer(self._native_window)
        self.io = imgui.get_io()
        self.open_dialog_state = False
        self.sti_file_dir = ".."
        self.selected = False
        self.fn_idx = 0

        # custom param
        self._poped = False


    def set_basic_widgets(self):
        if imgui.begin_main_menu_bar():
            if imgui.begin_menu("File", True):
                self.open_dialog_state, _ = imgui.menu_item("Open..", "", False, True)
                self._should_close, _ = imgui.menu_item(
                    "Quit", 'Cmd+Q', False, True
                )
                if self._should_close:
                    self.close()
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
                    if "terminate" in self.event_func_list:
                        self.dispatch_event("terminate")
                    self.import_sti_module((file_list[self.fn_idx].split('.')[0]))
                    self.set_sti_module(essential_func_name= ['prepare','set_widgets'], draw_func_name = None)
                    self.open_dialog_state = False

                imgui.same_line()
                if imgui.button("Cancel"):
                    self.open_dialog_state = False
                imgui.end_popup()

    def popable_opengl_component(self,comp_name,draw_func_name, pop_draw_func_name = None):
        if self.minion_manager:
            # _, self.window_state[1] = imgui.begin(comp_name, True)  # , flags = imgui.WINDOW_NO_TITLE_BAR)
            if not pop_draw_func_name:
                pop_draw_func_name = draw_func_name
            imgui.begin(comp_name, True)  # , flags = imgui.WINDOW_NO_TITLE_BAR)
            self.clear()
            self._framebuffer.activate()
            self.dispatch_event(draw_func_name)
            self._framebuffer.deactivate()
            draw_list = imgui.get_window_draw_list()
            ww, wh = imgui.get_window_size()
            winPos = imgui.get_cursor_screen_pos()
            draw_list.add_image(self._framebuffer.color[0]._handle, tuple(winPos),
                                tuple([winPos[0] + ww, winPos[1] + wh]),
                                (0, 0), (1, 1))
            imgui.invisible_button("pop", ww - 30, wh - 50)
            if imgui.begin_popup_context_item("Item Context Menu", mouse_button=0):
                if imgui.selectable("pop")[1]:
                    pop_pocket = {'comp_name':comp_name,'import_module_name':self.import_stipgm.__name__,'draw_func_name':pop_draw_func_name,'parent_name': self._name}
                    self.minion_manager.add_minion(comp_name, _popwin_frameworkfunc,custom_var = pop_pocket)
                    self.minion_manager.add_queue_connection(self._name+'<->'+comp_name)
                    self.minion_manager.run([comp_name])
                    self._poped = True
                imgui.end_popup()
            imgui.end()

    def process(self):
        self.dt = self._clock.tick()
        self.clear()
        self.imgui_renderer.process_inputs()
        imgui.new_frame()
        self.set_basic_widgets()
        self.dispatch_event("set_widgets")
        imgui.render()
        self.imgui_renderer.render(imgui.get_draw_data())
        # if len(self._pop_queue) > 0:
        #     for win_param in self._pop_queue:
        #         self._pop(*win_param)
        #         self._pop_queue.remove(win_param)
        #     self._has_pop = True
        # if (len([x for x in self._manager.__windows__ if x._name == 'pop']) == 0) and self._has_pop:
        #     self._has_pop = False
        #     self._dock()


    def close(self):
        self._should_close = True
        if "terminate" in self.event_func_list:
            self.dispatch_event("terminate")
        # if self._has_pop:
        #     for win in self._manager.__windows__[1:]:
        #         win.close()
        # else:
        #     pass
        self.imgui_renderer.shutdown()
        glfw.set_window_should_close(self._native_window, True)

def _popwin_frameworkfunc(hook):
    glplayer_win = glplayer(hook.get_pocket('comp_name'), 1024, 720, config=app.configuration.Configuration(),
                            minion_plug=hook)
    glplayer_win._parent = hook.get_pocket('parent_name')
    glplayer_win.import_sti_module(hook.get_pocket('import_module_name'))
    glplayer_win.set_sti_module(draw_func_name=hook.get_pocket('draw_func_name'))
    glplayer_win.run()
    sys.exit()
############## Legacy code ##############
    # def pop(self, width, height, pos_x, pos_y, title='GLWin'): # methods of glimwin
    #     self._pop_queue.append([int(width), int(height), int(pos_x), int(pos_y), title])
    #
    # def _pop(self, width, height, pos_x, pos_y, title):
    #     config = app.configuration.Configuration()
    #     config.stencil_size = 8
    #     popWin = adapted_glumpy_window('pop', width=width, height=height, color=(0, 0, 0, 1), title=title,
    #                                    config=config)
    #     popWin.set_position(pos_x, pos_y)
    #     # Every time create a new window requires reinitialize all programs and buffers
    #     self._texture_buffer = np.zeros((self.height, self.width, 4), np.float32).view(gloo.TextureFloat2D)
    #     self._depth_buffer = gloo.DepthBuffer(self.width, self.height)
    #     self._framebuffer = gloo.FrameBuffer(color=[self._texture_buffer], depth=self._depth_buffer)
    #     self._internal_draw_program["texture"] = self._texture_buffer
    #     # for func in self.event_func_list:
    #     #     if func in self.import_stipgm.__dict__:
    #     #         getattr(self.import_stipgm, func).__globals__['self'] = self
    #     #         self.event(getattr(self.import_stipgm, func))
    #     glumpy_func_list = ['on_init', 'on_draw', 'on_resize']
    #     for func in self.event_func_list:
    #         getattr(self.import_stipgm, func).__globals__['self'] = self
    #         self.event(getattr(self.import_stipgm, func))
    #         if func not in glumpy_func_list:
    #             self.register_event_type(func)
    #
    #     self.dispatch_event('prepare')
    #
    #     @popWin.event
    #     def on_draw(dt):
    #         self.import_stipgm.on_draw(self.dt)
    #
    #     popWin.ori_pos = np.array([(+1., +1.), (+1., -1.), (-1., +1.), (-1., -1.)])
    #     popWin.ori_ratio = self.width / self.height
    #
    #     @popWin.event
    #     def on_resize(width, height):
    #         self.import_stipgm.pop_on_resize(width, height)
    #
    #     popWin.dispatch_event('on_resize', width, height)
    #     self._manager.register_windows(popWin)
    #
    # def _dock(self):
    #     self._texture_buffer = np.zeros((self._init_height, self._init_width, 4), np.float32).view(gloo.TextureFloat2D)
    #     self._depth_buffer = gloo.DepthBuffer(self._init_width, self._init_height)
    #     self._framebuffer = gloo.FrameBuffer(color=[self._texture_buffer], depth=self._depth_buffer)
    #     self.dispatch_event('prepare')





# class glimManager:
#     __windows__ = []
#     __windows_to_remove__ = []
#     __name__ = 'GlImgui_GLFW'
#
#     def __init__(self):
#         glfw.init()
#
#     def register_windows(self, window: adapted_glumpy_window):
#         window._manager = self
#         self.__windows__.append(window)
#
#     def execute(self):
#         glfw.poll_events()
#         # TODO(solved?): FINALIZE HERE to make it behave like app.run
#         for window in self.__windows__:
#             if isinstance(window, adapted_glumpy_window):
#                 if glfw.window_should_close(window._native_window):
#                     self.__windows__.remove(window)
#                     self.__windows_to_remove__.append(window)
#                 else:
#                     window.activate()
#                     window.process()
#             window.swap()
#
#         for window in self.__windows_to_remove__:
#             window.destroy()
#             self.__windows_to_remove__.remove(window)
#
#     def run(self):
#         while len(self.__windows__) + len(self.__windows_to_remove__) > 0:
#             self.execute()
#         sys.exit()

