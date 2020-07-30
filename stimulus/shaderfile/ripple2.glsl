// Author:
// Title:

#ifdef GL_ES
precision mediump float;
#endif
#extension GL_OES_standard_derivatives: enable
uniform vec2 u_resolution;
uniform vec2 u_mouse;
uniform float u_time;
uniform float u_speed;

float random (in vec2 _st) {
    return fract(sin(dot(_st.xy,
                         vec2(12.9898,78.233)))*
        43758.5453123);
}
vec2 random2( vec2 p ) {
    return fract(sin(vec2(dot(p,vec2(127.1,311.7)),dot(p,vec2(269.5,183.3))))*43758.5453);
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

#define NUM_OCTAVES 5

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


float gauss_env(float p,float u,float sig){
    sig = min(sig+u,sig);
    return exp(-.5*pow(p-u,2.)/(sig*sig));
}

# define pi 3.1415926
# define NP 100
void main() {
    vec2 st = gl_FragCoord.xy/u_resolution.xy;
    st.x *= u_resolution.x/u_resolution.y;
    float v_time = u_time * u_speed;
    // st *=float(NP);
    vec2 i_st = floor(st);
    vec2 f_st = fract(st);
    float height = 0.000;
	 for (int i = 1; i <= NP; i++){
        vec2 iter_point = random2(vec2(float(i)));
         // l_st = min(l_st,fract(length(iter_point-f_st)*2.));
         float sigma = random(i_st+float(i))*28.;
         float spreading_speed = abs(random(i_st-float(i)))*20.;
         float spatial_freq = min(max(sqrt(spreading_speed)*100./sigma,10.),40.);
         float dist = length(iter_point-f_st)*spatial_freq*pi;
         float spatial_wrap = gauss_env(dist,sin(v_time/spreading_speed)*spreading_speed,sigma);
         float temporal_wrap = gauss_env(fract(v_time/sigma)*sigma,0.,spreading_speed/sigma);
         height += sin(dist-v_time*spreading_speed)*spatial_wrap/float(NP)*12.;
     }
    vec3 water_surface = vec3(st,height+0.692);
    vec3 X = dFdx(water_surface);
	 vec3 Y = dFdy(water_surface);
    vec3 normal = normalize(cross(X,Y));
    vec3 light_normal = normalize(vec3(st+.5,1.000));
    float eta = .3;
    float k = 1.0 - eta * eta * (1.0 - dot(normal, light_normal) * dot(normal, light_normal));
	 vec3 R = normalize(eta * light_normal - (eta * dot(normal, light_normal) + sqrt(k)) * normal)*15.;
    height += fbm(st*30.+v_time)/6.;
    vec2 grid = smoothstep(0.912,0.940,fract(st*15.+vec2(R.x*height,R.y*height)/800.))/1.;
    st += vec2(R.x*height,R.y*height);
    gl_FragColor = vec4(vec3(0.041,0.549,0.890)+max(grid.x,grid.y)/2.+max(vec3(1.-sqrt(length(st-.5))),0.),1.0);
}