// Author: @patriciogv
// Title: CellularNoise

#ifdef GL_ES
precision mediump float;
#endif

uniform vec2 u_resolution;
uniform vec2 u_mouse;
uniform float u_time;
uniform float coherence_lvl;
uniform float distortion_lvl;
uniform float distortion_scale;
uniform float stimulus_scale;

# define pi 3.141592653


float random (in vec2 _st) {
    return fract(sin(dot(_st.xy,
                         vec2(12.9898,78.233)))*
        43758.5453123);
}

// Based on Morgan McGuire @morgan3d
// https://www.shadertoy.com/view/4dS3Wd
float noise (in vec2 _st) {
    vec2 i = floor(_st);
    vec2 f = fract(_st);

    // Four corners in 2D of a tile
    float a = random(i);
    float b = random(i + vec2(1.0, 0.0));
    float c = random(i + vec2(0.0, 1.0));
    float d = random(i + vec2(1.0, 1.0));

    vec2 u = f * f * (3.0 - 2.0 * f);

    return mix(a, b, u.x) +
            (c - a)* u.y * (1.0 - u.x) +
            (d - b) * u.x * u.y;
}

#define NUM_OCTAVES 7

float fbm ( in vec2 _st) {
    float v = 0.0;
    float a = .5;
    vec2 shift = vec2(100.0);
    // Rotate to reduce axial bias
    mat2 rot = mat2(cos(0.5), sin(0.5),
                    -sin(0.5), cos(0.50));
    for (int i = 0; i < NUM_OCTAVES; ++i) {
        v += a * noise(_st);
        _st = rot*_st * 2.0 + shift;
        a *= 0.5;
    }
    return v;
}

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

vec2 fbm2 ( in vec2 _st) {
    vec2 v = vec2(0.0);
    float a = 0.5;
    vec2 shift = vec2(100.0);
    // Rotate to reduce axial bias
    mat2 rot = mat2(cos(0.5), sin(0.5),
                    -sin(0.5), cos(0.50));
    for (int i = 0; i < NUM_OCTAVES; ++i) {
        v += a * noise2(_st);
        _st = rot * _st * 2.0 + shift;
        a *= 0.5;
    }
    return v;
}

vec3 hsb2rgb( in vec3 c ){
    vec3 rgb = clamp(abs(mod(c.x*6.0+vec3(0.0,4.0,2.0),
                             6.0)-3.0)-1.0,
                     0.0,
                     1.0 );
    rgb = rgb*rgb*(3.0-2.0*rgb);
    return c.z * mix(vec3(1.0), rgb, c.y);
}
# define pi 3.141592653
void main() {
    vec2 st = gl_FragCoord.xy/u_resolution.xy*3.;
    st.x *= u_resolution.x/u_resolution.y;
    st -= u_mouse/u_resolution;
//    float coherence_lvl = 1.;
//    float distortion_lvl = 1.816;
//    float distortion_scale = 5.;
//    float stimulus_scale = 3.;
    float coherence_lvl2 = fract(coherence_lvl);
    
    // vec3 color = vec3(0.001,0.134,0.470);
	 st += cos(coherence_lvl2/2.*pi)*cos(coherence_lvl2/2.*pi)*u_time+sin(coherence_lvl2/2.*pi)*sin(coherence_lvl2/2.*pi)*fbm2(st+u_time);
    st *= stimulus_scale;
    
    vec2 k2 = fract(st+fbm2(st/distortion_scale)*distortion_lvl);
        
    vec3 mask = vec3(length(smoothstep(0.9,1.0,k2)));

    // gl_FragColor = vec4((f*f*f+.6*f*f+.5*f)*color,1.);
    gl_FragColor = vec4(mask,1.000);
}
