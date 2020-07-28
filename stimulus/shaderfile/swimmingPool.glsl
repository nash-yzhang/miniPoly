// Author:
// Title:

#ifdef GL_ES
precision mediump float;
#endif

uniform vec2 u_resolution;
uniform vec2 u_mouse;
uniform float u_time;
uniform float u_speed;
uniform float reflect_scale;
uniform float refract_scale;
uniform float reflect_weight;
uniform float refract_weight;
uniform float reflect_pow;
uniform float refract_pow;

#define pi 3.141592653

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

float wave(in vec2 st, in float power){
    // float wl = .3;
    // float wv = 1.;
    // float wamp = 1.;
    st += noise(st);
    vec2 stx = 1.0-abs(sin(st));
    vec2 sty = abs(cos(st));
    vec2 stxy = mix(stx,sty,stx);
    return pow(1.0-pow(stxy.x*stxy.y,0.65),power);
}

#define NOCT 4
float wave_oct(in vec2 st,in float speed){
    // float wl = .3;
    // float wv = 1.;
    // float wamp = 1.;
    float waveout = 0.;
    float power = 4.;
    float amp = 4.;
    vec2 _st = st/1.;
    // float speed = 1.;
    for (int i=0; i < NOCT; i++){
        st += noise(_st+u_time*speed); 
        waveout += wave(st,power)*amp;
        st += noise(st);
        st *= 1.248;
        power = mix(power,1.0,0.2);
        speed *= 2.;
        amp *= 1.5;
    }
    return waveout/16.;
}

vec3 getnormal(in vec3 p){
    return normalize(cross(p,vec3(1.,0.,0.)));
}

float getangle(in vec3 p1, in vec3 p2){
    return dot(normalize(p1),normalize(p2));
}

float snell(in vec3 p1, in vec3 p2, in float ratio){
    float sin_inangle = sqrt(1.-pow(getangle(p1,p2),2.));
    float sin_outangle = sin_inangle*ratio;
    return sin_outangle;
}

void main() {
    vec2 st = gl_FragCoord.xy/u_resolution.xy;
    st.x *= u_resolution.x/u_resolution.y;
    
	// st = st-.5;
    
    float height = wave_oct(st*refract_scale,u_speed)+wave_oct(st*refract_scale+vec2(.5),u_speed);
    float refraction = smoothstep(0.208,1.,pow(abs(sin(1.744-height+0.236*pi)),refract_pow))-.8;
    float height2 = wave_oct(st*reflect_scale+random(vec2(.5)),u_speed)+wave_oct(st*reflect_scale+random(vec2(.5)),u_speed);
    float reflection = smoothstep(0.056,1.424,pow(abs(sin(height2+0.804*pi)),reflect_pow))-.8;
    vec2 pat = smoothstep(0.908,1.0,sin(st*pi*7.848+height2/4.));
    vec3 color = (1.-(1.-max(pat.x,pat.y)+vec3(refraction)*refract_weight+vec3(reflection)*reflect_weight)*vec3(1.,.5,.3));
    // color = vec3(st.x,st.y,abs(sin(u_time)));

    gl_FragColor = vec4(color,1.0);
}