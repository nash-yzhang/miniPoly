uniform float u_time;
uniform vec2 u_resolution;
varying vec2 v_pos;
#define PI 3.1415926
void main() {
    vec2 st = v_pos;
    st.x *= u_resolution.x/u_resolution.y;
    vec3 color = vec3(0.);
    float dir = fract(u_time/50.)*2*PI;
    color = vec3(sin((sin(dir)*st.x+cos(dir)*st.y)*12.*PI+u_time*4*PI));
    float mask = step(length(st),.35);
    gl_FragColor = vec4(color*mask, 1.0);
}
