# define PI 3.14159265
uniform vec2 u_resolution;
uniform float u_time;
uniform float pat_scale;
uniform float speed;
uniform float stepthre;
uniform float dir;
void main() {
    vec2 st = gl_FragCoord.xy/u_resolution.xy;
    st.x *= u_resolution.x/u_resolution.y;
    st -= 0.5;
//    float stepthre = 0.224;
    mat2 rot_mat = mat2(cos(dir), sin(dir), -sin(dir), cos(dir));
    st = rot_mat*st;
    vec2 mov_pat = vec2(1.,0.)*u_time*speed;
    float pat_c = 0.;smoothstep(stepthre+.1,stepthre,distance(fract(st*pat_scale+vec2(0.610,0.470)),vec2(.5)))*step(0.5,sin(u_time*20.));
    float pat_b = smoothstep(stepthre,stepthre+.1,distance(fract(st*pat_scale-mov_pat),vec2(.5)));
    float pat_a = smoothstep(stepthre,stepthre+.1,distance(fract(st*pat_scale+mov_pat),vec2(.5)));
    gl_FragColor = vec4(1.-vec3(pat_a+pat_b)/2.,1.0);
}