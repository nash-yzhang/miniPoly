varying vec2 v_pos;
uniform float u_alpha;
uniform float u_time;
uniform float u_barpos;
void main() {
    float marker = step(.5,distance(gl_PointCoord,vec2(.5)));
    float color = sin(v_pos.x*20.+u_time*30.)/2.-.15+marker;
    float mask  = step(abs(gl_PointCoord.x-u_barpos),.1);
    gl_FragColor = vec4(vec3(color*mask), u_alpha);
}
