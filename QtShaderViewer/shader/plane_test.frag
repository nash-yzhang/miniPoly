uniform float u_time;
//uniform vec2 u_resolution;
varying vec2 v_pos;
#define PI 3.1415926
float plot(vec2 st, float pct){
    return  smoothstep( pct-0.02, pct, st.y) -
    smoothstep( pct, pct+0.02, st.y);
}
void main() {
    vec2 st = v_pos;
//    st.x *= u_resolution.x/u_resolution.y;
    float pct = sin(st.x*8*PI-2.*u_time)/2.*pow((st.x/2.+.5),1.2);
    vec3 color = vec3(pct);
    color = max(color,vec3(0,plot(st,pct),0));
//    vec3 color = vec3(0.);
//    float dir = fract(u_time/50.)*2*PI;
//    color = vec3(sin((sin(dir)*st.x+cos(dir)*st.y)*12.*PI+u_time*4*PI));
//    float mask = step(length(st),.35);
    gl_FragColor = vec4(color, 1.0);
}
