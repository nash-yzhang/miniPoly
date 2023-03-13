// Author: @patriciogv
// Title: CellularNoise

#ifdef GL_ES
precision mediump float;
#endif

uniform vec2 u_resolution;
uniform vec2 u_mouse;
uniform float u_time;

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
#define COctave 3
float cnoctave(in vec2 _st){
    float scale_incr  = 2.2;
    float amp = .5;
    float amp_incr = 1.;
    float min_scale = 2.;
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
void main() {
    vec2 st = gl_FragCoord.xy/u_resolution.xy;
    st.x *= u_resolution.x/u_resolution.y;
    vec3 color = vec3(.0);

    // Scale
    float m_dist = cnoctave(st);	

    // Draw the min distance (distance field)
    color += m_dist;//pow(m_dis);

    // Draw cell center
    // color += 1.-step(.02, m_dist);

    // Draw grid
    // color.b += (1.-step(0.95, f_st.x) - step(.95, f_st.y));
    // color += (step(0.95, f_st.x) + step(.95, f_st.y))/2.5;

    // Show isolines
    // color -= step(.7,abs(sin(27.0*m_dist)))*.5;

    gl_FragColor = vec4(color,1.0);
}
