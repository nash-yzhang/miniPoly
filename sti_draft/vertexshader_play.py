import numpy as np
from glumpy import app, gloo, gl, glm
import pims
from bin.glarage import load_shaderfile

vertex = """
    attribute vec3 position;
    uniform mat4   u_view;         // Model matrix
    varying vec3 vertex;
    void main()
    {
        vertex  = position;
        gl_Position = u_view*vec4(position, 1.0);
    }
"""

fragment = """
    #extension GL_OES_standard_derivatives : enable
    uniform vec2 u_resolution;
    uniform float u_time;
    varying vec3 vertex;
    void main() {
      // Pick a coordinate to visualize in a grid
      vec3 coord = vertex.xyz;
    
      // Compute anti-aliased world-space grid lines
      vec3 grid = abs(fract(coord - 0.5) - 0.5) / fwidth(coord);
      float line = min(min(grid.x, grid.y), grid.z);

    
      // Just visualize the grid lines directly
      gl_FragColor = vec4(vec3(1.-min(line,.5)), 1.0);
    }
"""

u_resolution = (500,500)

nl = 225
snl = np.sqrt(nl)
program = gloo.Program(vertex, fragment, count=nl)    

xdata,ydata = np.reshape(np.array(np.meshgrid(np.linspace(0,1,np.sqrt(nl)),np.linspace(0,1,np.sqrt(nl)))),[2,-1])
zdata = (np.sin(xdata*2*np.pi)+np.cos(ydata*2*np.pi))/2.+.5
program['position'] = np.vstack([xdata,ydata,zdata]).T
program['u_view'] = np.eye(4)
program['u_resolution'] = u_resolution
program['u_time'] = 0.

window = app.Window(width=u_resolution[0], height=u_resolution[1])
app.clock.set_fps_limit(40)


@window.event
def on_draw(dt):
    window.clear()

    program['u_time'] += dt
    program.draw(gl.GL_TRIANGLE_STRIP)

@window.event
def on_mouse_drag(x, y, dx, dy, buttons):
    model = np.eye(4, dtype=np.float32)
    glm.rotate(model, y, 0, 0, 1)
    glm.rotate(model, x, 0, 1, 0)
    program['u_view'] = model
app.run()


