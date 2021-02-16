from bin.glarage import *
from glumpy import gloo, glm,gl
import imgui, os, sys
import cv2
from datetime import datetime
from os.path import isfile
from PIL import Image
import numpy as np

self = None

def prepare():
    self.FPS = 60
    self._shader_folder = '../stimulus/shaderfile/' # frag shader dir
    self._texture_folder = '../stimulus/shaderfile/' # texture used in frag shader
    self._frag_shader_fn = None # frag shader file name
    self._texture_fn = None # texture file name
    self._frag = None # fragment shader
    self._frag_render_program = None # gl program for rendering with frag shader set
    self._default_param_val = {'float': 1., 'vec2': (1., 1.), 'u_time': 0., 'u_resolution': (512, 512),
                               'u_mouse': (0., 0.),
                               'position': [[-1, -1], [1, -1], [-1, 1], [1, 1]], 'texture': np.ones([10, 10])} # Default value for custom uniform
    self.frag_fn_idx = 0 #  buffered fragment shader file indx
    self.texture_fn_idx = 0 # buffered texture file indx
    self.load_shader_win = False
    self._changespeed = 0.1
    self.window_state = [True, True]

    self.vid_fn = datetime.now().strftime(".//Output_%H-%M-%S_%d%m%Y.avi")
    while isfile(self.vid_fn):
        self.vid_fn = datetime.now().strftime(".//Output_%H-%M-%S_%d%m%Y.avi")

    self.vidwriter = None
    self.rec_button_text = 'Start'
    self.rec_on = False

    self._clock.set_fps_limit(self.FPS)

    self._vertex = """
    attribute vec2 position;
    void main() {
        gl_Position = vec4(position, 0.0, 1.0 );
    }
    """


def setup_shader():
    self._frag = load_shaderfile(self._shader_folder + self._frag_shader_fn)
    self._frag_render_program = gloo.Program(self._vertex, self._frag)
    for u in self._frag_render_program.all_uniforms:
        if u[1] == gl.GL_FLOAT:
            self._frag_render_program[u[0]] = self._default_param_val['float']
        elif u[1] == gl.GL_FLOAT_VEC2:
            self._frag_render_program[u[0]] = self._default_param_val['vec2']
        elif u[1] == gl.GL_SAMPLER_2D:
            self._frag_render_program[u[0]] = self._default_param_val['texture']
        if u[0] == 'u_time':
            self._frag_render_program[u[0]] = self._default_param_val['u_time']
        elif u[0] == 'u_mouse':
            self._frag_render_program[u[0]] = self._default_param_val['u_mouse']
        elif u[0] == 'u_resolution':
            self._frag_render_program[u[0]] = self._default_param_val['u_resolution']

    self._frag_render_program['position'] = self._default_param_val['position']
    self.load_shader_win = False


def set_widgets():
    if imgui.begin_main_menu_bar():
        if imgui.begin_menu("Command", True):
            clicked_restart, _ = imgui.menu_item(
                "Restart GLwindow", '', False, True
            )
            if clicked_restart:
                self.window_state[1] = True
                if self._children:
                    self.minion_plug.remote_shutdown(self._children)
                    self._children = None
                    self._should_pop = self._poped
                    self._poped = False

            imgui.end_menu()
        if imgui.begin_menu("FragShader", True):
            self.load_shader_win, _ = imgui.menu_item(
                "Load", '', False, True
            )
            imgui.end_menu()
        imgui.end_main_menu_bar()

    if self.load_shader_win:
        imgui.set_next_window_size(400, 300)
        imgui.open_popup("Select file")
        if imgui.begin_popup_modal("Select file")[0]:
            _, self._shader_folder = imgui.input_text(' ', self._shader_folder, 256)
            if os.path.isdir(self._shader_folder):
                file_list = [file for file in os.listdir(self._shader_folder) if file.endswith(".glsl")]
            else:
                file_list = []
            _, self.frag_fn_idx = imgui.combo(
                "", self.frag_fn_idx, file_list
            )
            if imgui.button("Select"):
                sys.path.insert(0, self._shader_folder)
                self._frag_shader_fn = file_list[self.frag_fn_idx]
                setup_shader()
                if self._children and self._poped:
                    self.minion_plug.remote_shutdown(self._children)
                    self._children = None
                    self._should_pop = self._poped
                    self._poped = False
            imgui.same_line()
            if imgui.button("Cancel"):
                self.load_shader_win = False
            imgui.end_popup()

    if self._frag_render_program != None:
        imgui.begin("Control")
        if imgui.button("Reload", 120,20):
            setup_shader()
        imgui.new_line()
        expanded,_ = imgui.collapsing_header("Param Space", True)
        if expanded:
            if imgui.begin_popup_context_window(mouse_button=0):
                _, self._changespeed = imgui.drag_float('Change precision', self._changespeed, 0.1)
                imgui.end_popup()
            for u in self._frag_render_program.all_uniforms:
                if u[0] not in ['u_time', 'u_resolution','u_mouse']:
                    if u[1] == gl.GL_FLOAT:
                        _, self._frag_render_program[u[0]] = imgui.drag_float(u[0], self._frag_render_program[u[0]],
                                                                              self._changespeed)
                    elif u[1] == gl.GL_FLOAT_VEC2:
                        _, self._frag_render_program[u[0]] = imgui.drag_float2(u[0]+'folder', *self._frag_render_program[u[0]],
                                                                               self._changespeed)
                    elif u[1] == gl.GL_SAMPLER_2D:
                        _, self._texture_folder = imgui.input_text(u[0], self._texture_folder, 256)
                        if os.path.isdir(self._texture_folder):
                            file_list = [file for file in os.listdir(self._texture_folder)
                                         if file.endswith((".png", ".jpg", "jpeg", ".jfif", ".bmp"))]
                        else:
                            file_list = []
                        _, self.texture_fn_idx = imgui.combo(
                            "Select texture", self.texture_fn_idx, file_list
                        )
                        if imgui.button("Select"):
                            sys.path.insert(0, self._texture_folder)
                            self._texture_fn = file_list[self.texture_fn_idx]
                            temp = np.array(Image.open(self._texture_folder + self._texture_fn)) / 256
                            self._frag_render_program[u[0]] = temp.astype(np.float32).view(gloo.TextureFloat2D)
                            self._frag_render_program[u[0]].wrapping = gl.GL_REPEAT

        self.pop_check()
        if not self._poped:
            imgui.new_line()
            expanded2, _ = imgui.collapsing_header("Video Recording", True)
            if expanded2:
                _, vid_fn = imgui.input_text('', self.vid_fn, 1024)
                if vid_fn != self.vid_fn:
                    self.vid_fn = vid_fn
                    if self.vidwriter:
                        self.vidwriter.release()
                imgui.same_line()
                if imgui.button(self.rec_button_text):
                    if self.rec_on:
                        self.rec_button_text = 'Start'
                        self.rec_on = False
                        self.vidwriter.release()
                        self.vid_fn = datetime.now().strftime(".//Output_%H-%M-%S_%d%m%Y.avi")
                        print(self.vid_fn)
                    else:
                        self.rec_on = True
                        if self.rec_button_text == 'Start':
                            self.vidwriter = cv2.VideoWriter(self.vid_fn, cv2.VideoWriter_fourcc(*'XVID'), self.FPS,
                                                             (self._framebuffer.width, self._framebuffer.height))
                            self.rec_button_text = 'Stop'
            imgui.end()
            if hasattr(self._frag_render_program, 'u_mouse'):
                x, y = imgui.get_mouse_pos()
                self._frag_render_program['u_mouse'] = (x, y)
            if self.rec_on:
                data = (cv2.cvtColor(self._framebuffer.color[0].get(), cv2.COLOR_RGBA2RGB) * 255).astype(np.uint8)[:, :,
                       ::-1]
                self.vidwriter.write(data)

            self.popable_opengl_component("GLView", 'draw', pop_draw_func_name='client_draw')
        else:
            imgui.end()
            self.minion_plug.get(self._children)
            if 'waiting' in self.minion_plug.inbox.keys():
                if self.minion_plug.inbox['waiting']:
                    self.minion_plug.put(
                        {'frag_fn': self._shader_folder + self._frag_shader_fn, 'vertex_shader': self._vertex})
                    self.minion_plug.give(self._children, ['frag_fn', 'vertex_shader'])
                else:
                    varlist = [u[0] for u in self._frag_render_program.all_uniforms if
                               u[0] not in ['u_time', 'u_resolution', 'u_mouse']]
                    self.minion_plug.put({v: self._frag_render_program[v] for v in varlist})
                    self.minion_plug.give(self._children, varlist)
            else:
                varlist = [u[0] for u in self._frag_render_program.all_uniforms if
                           u[0] not in ['u_time', 'u_resolution', 'u_mouse']]
                self.minion_plug.put({v: self._frag_render_program[v] for v in varlist})
                self.minion_plug.give(self._children, varlist)

def client_draw():
    self.minion_plug.get(self._parent)
    if self._frag_render_program != None and self.frag_fn == self.minion_plug.inbox['frag_fn']:
        self.__dict__.update(self.minion_plug.fetch(self._fetchlist))
        try:
            for val in self._fetchlist.values():
                if val not in ['u_time', 'u_resolution','u_mouse']:
                    self._frag_render_program[val] = getattr(self, val)
            ww, wh = self._width, self._height
            self.dispatch_event('draw', ww, wh)
        except:
            print("Undefined rendering error [FR-r1]")
    else:
        self.__dict__.update(self.minion_plug.fetch({'frag_fn': 'frag_fn', 'vertex_shader': '_vertex'}))
        try:
            self._frag = load_shaderfile(self.frag_fn)
            self._frag_render_program = gloo.Program(self._vertex, self._frag)
            self._fetchlist = {u[0]: u[0] for u in self._frag_render_program.all_uniforms}
            self._frag_render_program['position'] = self._default_param_val['position']
            self.minion_plug.put({'waiting': False})
            self.minion_plug.give(self._parent, ['waiting'])
        except:
            self.minion_plug.put({'waiting': True})
            self.minion_plug.give(self._parent, ['waiting'])
            print("Errors occurred when loading the selected fragment shader [Err:FR-1]")

def draw(ww,wh):
    self.clear([1.,0.,0.,1.])
    gl.glEnable(gl.GL_BLEND)
    try:
        self._frag_render_program['u_resolution'] = (ww, wh)
        self._frag_render_program['u_time'] += self.dt
        self._frag_render_program.draw(gl.GL_TRIANGLE_STRIP)
    except:
        self._frag_render_program = None