varying vec2 v_pos;
uniform vec2 u_resolution;
uniform float u_radius;
uniform float u_time;

vec2 rotate(vec2 st, float angle) {
     mat2 rotationMatrix = mat2(cos(angle), -sin(angle), sin(angle), cos(angle)); // identity matrix
     return rotationMatrix * st;
}

vec2 rotate_around(vec2 st, vec2 cen, float angle) {
    return rotate(st-cen,angle);
}

float rectangle(vec2 st, vec2 cen, float width, float height) {
    st -= cen;
    return step(0.,st.x) * step(st.x,0.1) * step(0., st.y) * step(st.y,0.3);
}

float rot_rectangle(vec2 st, vec2 rec_cen, float width, float height, float rot_ang, vec2 rot_cen) {
    vec2 new_st = rotate_around(st,rot_cen,rot_ang)-rec_cen;
    return rectangle(new_st, rec_cen, width, height);
}

# define PI 3.141592653
void main() {
    vec2 st = v_pos.yx;
    st.x *= u_resolution.x/u_resolution.y;

    float width = .1;
    float height = .3;
    vec2 rec_cen = vec2(-width/4.,.1);

    float red_rot_ang = -(sin(u_time*6.)+1.)*PI/6.;
    vec2 red_rot_cen = vec2(0.100,0.30);
    float red_saber = rot_rectangle(st, rec_cen, width, height,red_rot_ang,red_rot_cen);

    float blue_rot_ang = (sin(u_time*6.)+1.)*PI/6.;
    vec2 blue_rot_cen = vec2(0.850,0.30);
    float blue_saber = rot_rectangle(st, rec_cen, width, height,blue_rot_ang,blue_rot_cen);
    vec3 color = vec3(red_saber,0.,blue_saber);
    gl_FragColor = vec4(1.,0.,1.,1.0);
}
