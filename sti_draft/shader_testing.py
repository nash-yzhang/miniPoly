import numpy as np
from vispy import gloo, app


def load_shaderfile(fn):
    with open(fn, 'r') as shaderfile:
        return (shaderfile.read())


vert = """
#version 130
attribute vec3 a_position;
attribute vec2 uv;
varying vec2 v_position;
void main (void) {
    v_position = uv;
    gl_Position = vec4(a_position, 1.0);
}
"""

frag = """
varying vec2 v_position;
uniform vec2 u_resolution;
void main() {
    vec2 st = v_position.xy;
    st.x *= u_resolution.y/u_resolution.x;
    st *= 2;
    st -= 1;
    vec2 st2 = gl_FragCoord.xy / u_resolution.xy;
    st2 *= 2;
    st2 -= 1;
    vec3 color = vec3(step(.25,length(st)),0.,step(.25,length(st2)));
    gl_FragColor = vec4(color,1.);
}
"""

class Canvas(app.Canvas):
    fbo_render_pos = np.array([[-1.0, -1.0, 0.0], [-1.0, +1.0, 0.0],
                               [+1.0, -1.0, 0.0], [+1.0, +1.0, 0.0, ]], np.float32)/4
    fbo_norm_pos     = np.array([[0.0, 0.0], [0.0, +1.0],
                               [+1.0, 0.0], [+1.0, +1.0]], np.float32)
    def __init__(self):
        np.random.seed(77)
        app.Canvas.__init__(self, keys='interactive', size=(500,500))

        self._program_inspect = gloo.Program(vert,frag)
        self._program_inspect['a_position'] = self.fbo_render_pos
        self._program_inspect['uv'] = self.fbo_norm_pos
        self._program_inspect['u_resolution'] = self.physical_size
        gloo.set_state(blend=True, blend_func=('src_alpha', 'one_minus_src_alpha'), clear_color='black')
        self._timer = app.Timer(1/50, connect=self.update, start=True)
        self._counter = 0
        self.show()

    def on_draw(self, event):
        gloo.clear()
        self._program_inspect.draw('triangle_strip')

    def on_resize(self, event):
        width, height = self.physical_size
        gloo.set_viewport(0, 0, width, height)
        self._program_inspect["u_resolution"] = [width, height]

if __name__ == '__main__':
    c = Canvas()
    app.run()

