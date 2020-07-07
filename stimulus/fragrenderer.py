from scipy.ndimage import gaussian_filter
from bin.glarage import *
from glumpy import gl, gloo
import imgui, os, sys
from PIL import Image

self = None


def prepare():
    self._clock.set_fps_limit(70)
    self._vertex = """
    precision highp float;
    precision highp int;
    attribute vec2 position;
    void main() {
        gl_Position = vec4(position, 0.0, 1.0 );
    }
    """
    self._shader_folder = 'stimulus/shaderfile/'
    self._texture_folder = 'stimulus/shaderfile/'
    self._frag_shader_fn = None
    self._texture_fn = None
    self._frag = None
    self._frag_render_program = None
    self._default_param_val = {'float':1.,'vec2': (1.,1.),'u_time':0.,'u_resolution':(512,512),
                               'position':[[-1,-1],[1,-1],[-1,1],[1,1]],'texture':np.ones([10,10])}
    self.frag_fn_idx = 0
    self.texture_fn_idx = 0
    self.load_shader_win = False
    self._poped = False
    self._setpoped = False
    self._changespeed = 0.1
    self._refresh_on = False

def set_widgets():
    if imgui.begin_main_menu_bar():
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
                self._frag = load_shaderfile(self._shader_folder + self._frag_shader_fn)
                self._frag_render_program = gloo.Program(self._vertex,self._frag)
                for u in self._frag_render_program.all_uniforms:
                    if u[1] == gl.GL_FLOAT:
                        self._frag_render_program[u[0]] = self._default_param_val['float']
                    elif u[1] == gl.GL_FLOAT_VEC2:
                        self._frag_render_program[u[0]] = self._default_param_val['vec2']
                    elif u[1] == gl.GL_SAMPLER_2D:
                        self._frag_render_program[u[0]] = self._default_param_val['texture']
                    if u[0] == 'u_time':
                        self._frag_render_program[u[0]] = self._default_param_val['u_time']
                    elif u[0] == 'u_resolution':
                        self._frag_render_program[u[0]] = self._default_param_val['u_resolution']

                self._frag_render_program['position'] = self._default_param_val['position']
                self._refresh_on = True
                self.load_shader_win = False
            imgui.same_line()
            if imgui.button("Cancel"):
                self.load_shader_win = False
            imgui.end_popup()

    if self._frag_render_program != None:
        imgui.begin("Param Space")
        if imgui.begin_popup_context_window(mouse_button=0):
            _,self._changespeed = imgui.drag_float('Change precision',self._changespeed,0.1)
            imgui.end_popup()
        for u in self._frag_render_program.all_uniforms:
            if u[0] not in ['u_time','u_resolution']:
                if u[1] == gl.GL_FLOAT:
                    _,self._frag_render_program[u[0]] = imgui.drag_float(u[0],self._frag_render_program[u[0]],self._changespeed)
                elif u[1] == gl.GL_FLOAT_VEC2:
                    _,self._frag_render_program[u[0]] = imgui.drag_float2(u[0], *self._frag_render_program[u[0]],self._changespeed)
                elif u[1] == gl.GL_SAMPLER_2D:
                        _, self._texture_folder = imgui.input_text(' ', self._texture_folder, 256)
                        if os.path.isdir(self._texture_folder):
                            file_list = [file for file in os.listdir(self._shader_folder) if file.endswith((".png",
                                                                                                            ".jpg",
                                                                                                            "jpeg",
                                                                                                            ".bmp"))]
                        else:
                            file_list = []
                        _, self.texture_fn_idx = imgui.combo(
                            "", self.texture_fn_idx, file_list
                        )
                        if imgui.button("Select"):
                            sys.path.insert(0, self._texture_folder)
                            self._texture_fn = file_list[self.texture_fn_idx]
                            temp = np.array(Image.open(self._texture_folder+self._texture_fn))/256
                            self._frag_render_program[u[0]] = temp.astype(np.float32).view(gloo.TextureFloat2D)
        imgui.end()

        self.pop_check()
        if not self._poped:
            self.popable_opengl_component("GLView", 'draw', pop_draw_func_name='client_draw')
        else:
            self.minion_plug.get(self._children)
            if 'waiting' in self.minion_plug.inbox.keys() or self._refresh_on:
                if self.minion_plug.inbox['waiting']:
                    self.minion_plug.put({'frag_fn': self._shader_folder + self._frag_shader_fn, 'vertex_shader': self._vertex})
                    self.minion_plug.give(self._children, ['frag_fn', 'vertex_shader'])
                else:
                    self._refresh_on = False
                    varlist = [u[0] for u in self._frag_render_program.all_uniforms if
                               u[0] not in ['u_time', 'u_resolution']]
                    self.minion_plug.put({v: self._frag_render_program[v] for v in varlist})
                    self.minion_plug.give(self._children, varlist)
            else:
                self.minion_plug.put({'frag_fn': self._shader_folder + self._frag_shader_fn, 'vertex_shader': self._vertex})
                self.minion_plug.give(self._children, ['frag_fn', 'vertex_shader'])



def client_draw():
    self.minion_plug.get(self._parent)
    if self._frag_render_program != None:
        self.__dict__.update(self.minion_plug.fetch(self._fetchlist))
        try:
            for val in self._fetchlist.values():
                if val not in ['u_time', 'u_resolution']:
                    self._frag_render_program[val] = getattr(self,val)
            ww, wh = self._width, self._height
            self.dispatch_event('draw', ww, wh)
        except:
            pass
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




def draw(ww, wh):
    self.clear()
    gl.glEnable(gl.GL_BLEND)
    try:
        self._frag_render_program['u_resolution'] = (wh,ww)
        self._frag_render_program['u_time'] += self.dt
        self._frag_render_program.draw(gl.GL_TRIANGLE_STRIP)
    except:
        self._frag_render_program = None
