// Author @patriciogv - 2015
// http://patriciogonzalezvivo.com
#ifdef GL_ES
precision highp float;
#endif
uniform vec2 u_resolution;
uniform sampler2D u_tex;
uniform float u_time;
uniform float u_speed;
float random1 (in float val){
    return fract(sin(val*43758.5453123));
}

float random (in vec2 st) {
    return fract(sin(dot(st.xy,
                         vec2(12.9898,78.233))*100.)*
        439.929);
}
// Based on Morgan McGuire @morgan3d
// https://www.shadertoy.com/view/4dS3Wd


float noise (in vec2 st) {
    vec2 i = floor(st);
    vec2 f = fract(st);
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

//#define supsamp 3
//float noise_supsamp (in vec2 st) {
//    float val = 0.;
//    float supsampF = float(supsamp);
//    for (int ix = 0; ix < supsamp; ix++) {
//        for (int iy = 0; iy < supsamp; iy++) {
//            float fix = float(ix)/supsampF;
//            float fiy = float(iy)/supsampF;
//        	vec2 st1 = st+vec2(fix,fiy)/u_resolution;
//        	val+=noise(st1);
//        }
//    }
//    return val/supsampF/supsampF;
//}

#define OCTAVES 4
float fbm (in vec2 st) {
    // Initial values
    float value = 0.0;
    float amplitude = .5;
    float octave = float(OCTAVES);
    float amp_incr = .5;
    float scale_incr = 2.;
    float amp_sum = (1-pow(amp_incr,OCTAVES+1))/(1-amp_incr);
    // Loop of octaves
    for (int i = 0; i < OCTAVES; i++) {
        value += amplitude * noise(st) / amp_sum;
        st *= scale_incr ;
        amplitude *= amp_incr;
    }
    return value;
}


#define supsamp 3
float fbm_supsamp (in vec2 st) {
    float val = 0.;
    float supsampF = float(supsamp);
    for (int ix = 0; ix < supsamp; ix++) {
        for (int iy = 0; iy < supsamp; iy++) {
            float fix = float(ix)/supsampF;
            float fiy = float(iy)/supsampF;
        	vec2 st1 = st+vec2(fix,fiy)/u_resolution;
        	val+=fbm(st1);
        }
    }
    return val/supsampF;
}

#define pi 3.141592653
#define overlay 10
void main() {
    vec2 st = gl_FragCoord.xy/u_resolution.xy/4.;
    st.x *= u_resolution.x/u_resolution.y;
    st.y = -st.y;
    vec3 color = vec3(0.0);
    float total_i = float(overlay);
    float ii = 0.;
//    float vf_angle = *pi*2.;
    float vf_angle = texture2D(u_tex,st/1.5).r*4*pi;
    vec2 vf = vec2(sin(vf_angle),cos(vf_angle));;
    for (int i = 0; i<overlay;i++){
//        color += texture2D(u_tex,st+0.11*vf*fract(u_time/cycle_period+ii/total_i)).rgb*length(sin(fract(u_time/cycle_period+ii/total_i)*pi))/total_i;
        vec2 buffer_pos = (st*40. + random1(ii*ii)*30. +vf*fract(u_time*u_speed+ii/total_i));
   		color += fbm_supsamp(buffer_pos)*length(sin(fract(u_time*u_speed+ii/total_i)*pi))/total_i*1.5;
       ii += 1.;
    }
    gl_FragColor = vec4(color,1.0);
}