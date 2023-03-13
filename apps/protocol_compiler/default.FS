varying vec2 v_pos;
uniform vec2 u_resolution;
uniform float u_radius;

# define PI 3.141592653
void main() {
    vec2 st = v_pos/2+.5;
    st.x *= u_resolution.x/u_resolution.y;

    vec3 color = vec3(step(distance(st,vec2(0.5)),u_radius));
    gl_FragColor = vec4(color,1.0);
}
