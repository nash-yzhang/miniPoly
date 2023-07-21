from vispy import gloo
import numpy as np
from miniPoly.util.display import GLRenderer

class Renderer(GLRenderer):

    def __init__(self,canvas):
        super().__init__(canvas)
        self.VS = """
            #version 130
            attribute vec2 a_pos;
            varying vec2 v_pos;
            void main () {
                v_pos = a_pos;
                gl_PointSize = 10.;
                gl_Position = vec4(a_pos, 0.0, 1.0);
            }
            """

        self.FS = """
            varying vec2 v_pos;
            uniform sampler2D u_tex; 
            void main() {
                gl_FragColor = texture2D(u_tex,v_pos/2.+.5);
            }
        """
        self.program = gloo.Program(self.VS,self.FS)

    def init_renderer(self):
        self.program['a_pos'] = np.array([[-1.,-1.],[-1.,1.],[1.,-1.],[1.,1.]],np.float32)#/2.
        self.imCoordToRender = np.meshgrid(np.linspace(0,2*np.pi,100),np.linspace(0,2*np.pi,100))[0]*5.
        self.imageToRender = np.sin(self.imCoordToRender).astype(np.float32)
        self.program['u_tex'] = self.imageToRender
        gloo.set_state("translucent")

    def on_draw(self,event):
        gloo.clear('white')
        print(212121212)
        u_time = self.canvas.timer.elapsed
        self.imageToRender = np.sin(self.imCoordToRender+u_time%(2.*np.pi)*2.).astype(np.float32)
        self.program['u_tex'] = self.imageToRender
        self.program.draw('triangle_strip')
