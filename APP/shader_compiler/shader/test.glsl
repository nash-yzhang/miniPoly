varying vec2 v_pos;
uniform vec2 u_resolution;
uniform float u_time;
uniform float u_speed;

void main() {
    vec2 st = v_pos/2+.5;
    st.x *= u_resolution.x/u_resolution.y;

    vec3 color = vec3(0.);
    color = vec3(smoothstep(abs(sin(st.x*st.x*20.+u_time*u_speed)/4.+.5-st.y),0.01,.0));
    gl_FragColor = vec4(color,1.0);
}