import imgui
from time import time

self = None

def prepare():
    self._clock.set_fps_limit(50)
    self.azi = 0
    self.elv = 0
    self.dist = -5
    self.window_state = [True, True]
    self._init_glwin = True
    self._glwinpos = [0,0]
    self.bgcolor = 0, 0.5, 1, 1
    self.azi = 0
    self.elv = 0
    self.dist = -5
    self.t = 0
    self.cdt = 0
    self.timer =  time()

def set_widgets():
    imgui.begin("Controller", True)
    _, self.elv = imgui.slider_float("Azi", self.elv, 0, 360)
    _, self.azi = imgui.slider_float("Elv", self.azi, 0, 360)
    _, self.dist = imgui.slider_float("Dist", self.dist, -2, -10)
    _, self.bgcolor = imgui.color_edit4('test', *self.bgcolor, True)
    imgui.text("FPS: %d"%(1/(self.cdt+1e-8)))
    imgui.end()

    self.minion_plug.put(self,['elv','azi','dist','bgcolor','t'])
    self.minion_plug.give('display',['elv','azi','dist','bgcolor','t'])
    self.minion_plug.get('display', ['t'])
    if 't' in self.minion_plug.inbox.keys():
        if self.minion_plug.inbox['t'] > self.t:
            arc_t = self.timer
            self.timer = time()
            self.cdt = self.timer-arc_t
            self.t = self.minion_plug.inbox['t']
            # print(self.timer)


# def pop_on_resize(width,height):
#     self.quad['u_projection'] = glm.perspective(45.0, max(width,1.) / max(height,1.), 2.0, 100.0)

# def on_draw(dt):
#     self.clear(self.bgcolor)
#     gl.glEnable(gl.GL_DEPTH_TEST)
#     self.quad.draw(gl.GL_TRIANGLES, self.I)
