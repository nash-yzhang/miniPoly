import quaternion as qn
import sphModel as sp
import numpy as np
from sphViewer import *

exc_RF = '''
#version 120
#include "shader/sphCMN/trialg_tools.glsl"
uniform vec2 u_resolution;

float gaussfunc(in vec2 st, in vec2 mean, in float sigma) {
    float cen_x = distance(st,mean);
    return exp(-cen_x*cen_x/(2.*sigma));
}


void main() {
    vec2 st = gl_FragCoord.xy/u_resolution.xy;
    st.x *= u_resolution.x/u_resolution.y;
    float ext_mask = gaussfunc(st,vec2(0.5),0.04/10.)/2.;
    vec2 stvec = ext_mask*(st-.5)/length(st-.5);	
    float stangle = atan(stvec.y,stvec.x);
    vec3 ds = vec3(sin(stangle),sin(stangle+PI*2./3.),sin(stangle+PI*4./3.));
    ds /= length(ds);
    ds *= length(stvec); 
    gl_FragColor = vec4(ds,1.0);
}
'''

shaderViewer(exc_RF)
app.run()