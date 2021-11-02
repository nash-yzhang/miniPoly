uniform float u_time;
uniform vec2 u_resolution;
varying vec2 v_pos;
void main() {
    vec2 st = v_pos;
    st.x *= u_resolution.x/u_resolution.y;
    st *= 2.;
    st = fract(st);
    vec3 color = vec3(step(distance(st,vec2(.5)),.1));
    gl_FragColor = vec4(color, 1.0);
}
