import numpy as np
from glumpy import app, gloo, gl, glm
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
    uniform vec3 u_dot;
    uniform float u_time;
    void main()
    {
        vec2 uv_pos = gl_FragCoord.xy/u_resolution.xy*vec2(PI*2,PI)-vec2(PI,PI/2);
        vec4 cart_pos = vec4(cos(uv_pos.x)*cos(uv_pos.y),sin(uv_pos.x)*cos(uv_pos.y),sin(uv_pos.y),1.);
        cart_pos.xyz += vec3(sin(u_time)*cos(u_time),cos(u_time)*cos(u_time),cos(u_time))/10.;
        cart_pos.xyz /= length(cart_pos.xyz);
        cart_pos = u_view*cart_pos;
        float D = .3;
        float L = length(u_dot);
        float scalefac = 1/sqrt(D*D/4.+L*L); 
        float projD = D*scalefac;
        float projL = L*scalefac;
        float tempmask = smoothstep(projD/2.,projD/2.+0.01,distance(u_dot/L*projL,cart_pos.xyz));
        float colormask = 1.-cart_pos.z;
        vec2 uv_pos_2 = vec2(atan(cart_pos.x,cart_pos.y),asin(cart_pos.z))/vec2(PI*2,PI)+vec2(.5,.5);
        gl_FragColor = texture2D(texture, uv_pos_2.xy)*tempmask+vec4(vec3((1.-tempmask)*colormask),1.);
    }
"""
v = pims.Video('720_ANSEL_Kissed_AUG_15.mov')
total_frames = v.__len__()
T = v[0]
# T = np.array(Image.open("C:\\Users\\yzhang\\Documents\\GitHub\\miniPoly\\stimulus\\download2.png"))/256
u_resolution = T.shape[1::-1]
window = app.Window(width=u_resolution[0], height=u_resolution[1])
app.clock.set_fps_limit(60)

old_vec = 0
older_vec = 0
iframe = 0
@window.event
def on_draw(dt):
    global iframe, old_vec, older_vec
    window.clear()
    old_vec = old_vec/2. + np.random.randn(3)/50.
    older_vec = older_vec/2. + old_vec
    program['u_dot'] += older_vec
    program['u_time'] += dt
    T = v[iframe % total_frames]
    iframe+=1
    program['texture'] = T.view(gloo.Texture2D)
    program.draw(gl.GL_TRIANGLE_STRIP)


@window.event
def on_mouse_motion(azi, elv, dx, dy):
    azi *= -360 / u_resolution[0]
    azi -= 180
    elv *= -180 / u_resolution[1]
    elv -= 90
    program['u_view'] = glm.rotate(np.eye(4), azi * 5, 0, 0, 1) @ glm.rotate(np.eye(4), elv * 5, 1, 0, 0)

program = gloo.Program(vertex, fragment, count=4)
program['position'] = [(-1, -1), (-1, +1), (+1, -1), (+1, +1)]
program['u_dot'] = [1.,0.,0.]
program['u_resolution'] = u_resolution
program['u_view'] = np.eye(4)
program['u_time'] = 0.
program['texture'] = T.view(gloo.Texture2D)
program['texture'].wrapping = gl.GL_REPEAT

app.run()
