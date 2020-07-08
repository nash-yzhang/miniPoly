import numpy as np
from glumpy import app, gloo, gl,glm
import pims

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

fragment = """
    #define PI 3.1415926538
    uniform sampler2D texture;
    uniform vec2 u_resolution;
    uniform mat4 u_view;
    
    uniform float u_time;
    void main()
    {
        vec2 uv_pos = gl_FragCoord.xy/u_resolution.xy*vec2(PI*2,PI)-vec2(PI,PI/2);
        vec4 cart_pos = vec4(cos(uv_pos.x)*cos(uv_pos.y),sin(uv_pos.x)*cos(uv_pos.y),sin(uv_pos.y),1.);
        cart_pos = u_view*cart_pos;
        vec2 uv_pos_2 = vec2(atan(cart_pos.x,cart_pos.y),asin(cart_pos.z))/vec2(PI*2,PI)+vec2(.5,.5);
        gl_FragColor = texture2D(texture, uv_pos_2.xy);
    }
"""
v = pims.Video('C:\\Users\\yzhang\\Documents\\GitHub\\miniPoly\\stimulus\\720_ANSEL_Kissed_AUG_15.mov')
total_frames = v.__len__();
T = v[0]/256
# T = np.array(Image.open("C:\\Users\\yzhang\\Documents\\GitHub\\miniPoly\\stimulus\\download2.png"))/256
u_resolution = T.shape[1::-1]
window = app.Window(width=u_resolution[0], height=u_resolution[1])
app.clock.set_fps_limit(40)

@window.event
def on_draw(dt):
    global iframe
    window.clear()
    iframe+=1

    program['u_time'] += dt

    T = v[iframe%total_frames] / 256
    program['texture'] = T.astype(np.float32).view(gloo.TextureFloat2D)
    program.draw(gl.GL_TRIANGLE_STRIP)


@window.event
def on_mouse_motion(azi, elv, dx, dy):
    azi *= -360 / u_resolution[0]
    azi -= 180
    elv *= -180 /u_resolution[1]
    elv -= 90
    program['u_view'] = glm.rotate(np.eye(4), azi*5, 0, 0, 1) @ glm.rotate(np.eye(4), elv*5, 1, 0, 0)
    # print(program['u_view'])

program = gloo.Program(vertex, fragment, count=4)
program['position'] = [(-1,-1), (-1,+1), (+1,-1), (+1,+1)]
program['u_resolution'] = u_resolution
program['u_view'] = np.eye(4)
program['u_time'] = 0.
iframe = 0

program['texture'] = T.astype(np.float32).view(gloo.TextureFloat2D)
program['texture'].wrapping = gl.GL_REPEAT

app.run()