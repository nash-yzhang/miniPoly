from vispy import gloo
import numpy as np
from bin.glsl_preset import renderer

class Renderer(renderer):

    def __init__(self, canvas):
        super().__init__(canvas)
        # Define Vertice shader
        self.VS = """
            #version 130
            attribute vec2 a_pos;
            varying vec2 v_pos;
            void main () {
                v_pos = a_pos;
                gl_Position = vec4(a_pos, 0.0, 1.0);
            }
            """

        # Define Fragment shader
        self.FS = """
            varying vec2 v_pos; 
            uniform vec2 u_dot_pos; 
            uniform float u_time; 
            uniform vec2 u_resolution; 
            uniform float u_outerD;
            uniform float u_innerD;
            void main() {
                vec2 st = v_pos.yx;
                st.x *= u_resolution.y/u_resolution.x;
                float outerCirc = smoothstep(u_outerD,u_outerD*.9,distance(st,u_dot_pos+sin(u_time))); 
                float innerCirc = smoothstep(u_innerD,u_innerD*.9,distance(st,u_dot_pos+sin(u_time))); 
                float color = outerCirc-innerCirc;
                gl_FragColor = vec4(vec3(color),step(0.1,color));
            }
        """

        # Create rendering program
        self.program = gloo.Program(self.VS, self.FS)

    def init_renderer(self):
        # Initialize graphic model and uniforms
        self.program['a_pos'] = np.array([[-1., -1.], [-1., 1.], [1., -1.], [1., 1.]], np.float32)  # /2.
        self.program['u_time'] = 0
        self.program['u_resolution'] = (self.canvas.size[0],self.canvas.size[1])
        gloo.set_state("translucent",depth_test=False,blend=True,blend_func=('src_alpha', 'one_minus_src_alpha'))
        self.obj_init()
        self.started_time = self.canvas.timer.elapsed

    def on_draw(self, event):
        # Define the update rule
        gloo.clear([0,0,0,0])
        u_time = self.canvas.timer.elapsed - self.started_time
        self.obj_exec(u_time)
        self.program.draw('triangle_strip')

    def on_resize(self, event):
        # Define how should be rendered image should be resized by changing window size
        gloo.set_viewport(0, 0, *self.canvas.physical_size)
        self.program['u_resolution'] = (self.canvas.size[0],self.canvas.size[1])

    def obj_init(self):
        self.program['u_outerD'] = 0.
        self.program['u_innerD'] = 0.
        self.program['u_dot_pos'] = (0.,0.)
        self.obj_commands = [("obj_pause",1),("obj_appear",1)]

    def obj_pause(self,elps_t,total_t):
        self.program['u_outerD'] = 0.03*1.1
        self.program['u_innerD'] = 0.03*.99

    def obj_appear(self,elps_t,total_t):
        targetOD = 0.3
        startOD = 0.03
        edgeRatio = 0.1
        timePercent = elps_t/total_t
        self.program['u_outerD'] = ((targetOD-startOD)*timePercent+startOD)*(1+edgeRatio)
        self.program['u_innerD'] = ((targetOD-startOD)*timePercent+startOD)*(1-edgeRatio)


    def obj_exec(self,elapsed_time):
        for i in self.obj_commands:
            if elapsed_time>i[1]:
                elapsed_time -= i[1]
            else:
                iter_func = getattr(self,i[0])
                iter_func(elapsed_time,i[1])
                break