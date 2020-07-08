import numpy as np
from glumpy import app, gloo, gl, glm
import pims
from bin.glarage import load_shaderfile

vertex = """
    attribute vec2 position;
    attribute vec2 texcoord;
    varying vec2 v_texcoord;
    void main()
    {
        gl_Position = vec4(position, 0.0, 1.0);
        v_texcoord = texcoord;
    }
"""

fragment = load_shaderfile('C:\\Users\\yzhang\\Documents\\GitHub\\miniPoly\\stimulus\\shaderfile\\CMNV2b1.glsl')

v = pims.Video('C:\\Users\\yzhang\\Documents\\GitHub\\miniPoly\\stimulus\\720_ANSEL_Kissed_AUG_15.mov')
total_frames = v.__len__()
T = v[0][:,:,1] / 256
# T = np.array(Image.open("C:\\Users\\yzhang\\Documents\\GitHub\\miniPoly\\stimulus\\download2.png"))/256
u_resolution = T.shape[1::-1]
window = app.Window(width=u_resolution[0], height=u_resolution[1])
app.clock.set_fps_limit(40)


@window.event
def on_draw(dt):
    global iframe
    window.clear()
    iframe += 1

    program['u_time'] += dt

    T = v[iframe % total_frames][:,:,1]/ 256
    program['u_tex'] = T.astype(np.float32).view(gloo.TextureFloat2D)
    program['u_tex'].wrapping = gl.GL_REPEAT
    program.draw(gl.GL_TRIANGLE_STRIP)


program = gloo.Program(vertex, fragment, count=4)
program['position'] = [(-1, -1), (-1, +1), (+1, -1), (+1, +1)]
program['u_resolution'] = u_resolution
program['u_time'] = 0.
iframe = 0

program['u_tex'] = T.astype(np.float32).view(gloo.TextureFloat2D)
program['u_tex'].wrapping = gl.GL_REPEAT

app.run()