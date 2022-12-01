# define PI 3.14159265
uniform vec2 u_resolution;
uniform vec2 u_mouse;
uniform float u_time;

void main() {
    vec2 st = gl_FragCoord.xy/u_resolution.xy;
    st.x *= u_resolution.x/u_resolution.y;
    st -= 0.5;
    float d = 0.584;
    float distort_scale = pow(cos(atan(distance(st,vec2(0.))/d)),2.);
    float pat_scale = 30.*distort_scale;
    float mov_dir = PI*2.*.25;
    float mov_speed = 1.;
    vec2 mov_pat = vec2(sin(mov_dir),cos(mov_dir))*u_time*mov_speed;
    float pat_a = smoothstep(0.5,.6,distance(fract(st*pat_scale+mov_pat),vec2(.5)));
    float pat_b = 1.-smoothstep(0.1,0.2,distance(fract(st*pat_scale-mov_pat),vec2(.5)));
    vec3 color = vec3(0.);
    color = vec3(pat_a+pat_b)/1.5+.15;

    gl_FragColor = vec4(color,1.0);
}