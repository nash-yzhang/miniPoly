uniform float u_time;
varying vec2 v_pos;
#define PI 3.1415926
vec2 random2( vec2 p ) {
    return fract(sin(vec2(dot(p,vec2(127.1,311.7)),dot(p,vec2(269.5,183.3))))*43758.5453);
}

vec2 noise2 (in vec2 st){
    vec2 i_st = floor(st);
    vec2 f_st = fract(st);

    vec2 corner[4];
    corner[0] = random2(i_st);
    corner[1] = random2(i_st+vec2(1.,0.));
    corner[2] = random2(i_st+vec2(0.,1.));
    corner[3] = random2(i_st+vec2(1.,1.));
    vec2 u = f_st * f_st * (3.0 - 2.0 * f_st);
    // vec2 mixgradient = mix4(f_st,vec2(0.,0.),vec2(0.,1.),vec2(1.,0.),vec2(1.,1.));
    return mix(corner[0], corner[1], u.x) +
            (corner[2] - corner[0])* u.y * (1.0 - u.x) +
            (corner[3] - corner[1]) * u.x * u.y;
    // return mix(mix(corner[0],corner[1],f_st.y),mix(corner[2],corner[3],f_st.y),f_st.x);
}

float cellular_noise(in vec2 _st, in int side_scale){
    float m_dist = 1.;
    // Tile the space
    vec2 i_st = floor(_st);
    vec2 f_st = fract(_st);

    for (int y= -1; y <= 1; y++) {
        for (int x= -1; x <= 1; x++) {
            // Neighbor place in the grid
            vec2 neighbor = vec2(float(x),float(y));

            // Random position from current + neighbor place in the grid
            vec2 point = random2(i_st + neighbor);

            // Animate the point
            point += .5*noise2(_st+u_time);//0.5 + 0.5*sin(u_time + 6.2831*point);

            // Vector between the pixel and the point
            vec2 diff = neighbor + point - f_st;

            // Distance to the point
            float dist = length(diff);

            // Keep the closer distance
            m_dist = min(m_dist, dist);
        }
    }

    return m_dist;
}
#define COctave 5
float cnoctave(in vec2 _st){
    float scale_incr  = 1.2;
    float amp = .5;
    float amp_incr = 1.25;
    float min_scale = 5.;
    int side_scale = int((min_scale-1.)/2.);
    float m_dist = 0.;
	 _st *= min_scale;
    for (int CO=0;CO<COctave;CO++){
        m_dist += pow(amp*(cellular_noise(_st+random2(vec2(float(CO))),side_scale)),2.);
        amp *= amp_incr;
    	  _st *= scale_incr;
        side_scale *= int(scale_incr);
     }
    return m_dist;
}


# define pi 3.1415926
void main() {
    vec2 st = v_pos;
    st /= 1.5;

	// st = st-.5;
    vec3 m_dist = vec3(cnoctave(st-.02),cnoctave(st),cnoctave(st+.02));
    vec2 pat = smoothstep(0.908,1.0,sin(st*pi*20.+m_dist.z/2.));
    m_dist.x = pow(m_dist.x,3.);
    m_dist.y = pow(m_dist.y,3.);
    m_dist.z = pow(m_dist.z,3.);

    vec3 color = (1.-(1.-max(pat.x,pat.y))*vec3(1.,.5,.3))+min(m_dist/3.,4.)/4.;
//    vec3 color = vec3(sin(st.x));
    // color = vec3(st.x,st.y,abs(sin(u_time)));

//    gl_FragColor = vec4(vec3(cos(u_time+pi/3)/2.+.5,sin(u_time)/2.+.5,cos(u_time)/2.+.5),1.0);
    gl_FragColor = vec4(color,1.0);
}