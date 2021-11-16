varying vec3 v_pos;
uniform float u_time;
#define PI 3.14159265
float atan2(in float y, in float x)
{
    float norm = length(vec2(x,y));
    x /= norm;
    return mix(acos(x),-acos(x),int(y>0));
}

vec2 cart2sph(in vec3 cart_coord)
{
    //    TODO: something wrong here, fix it!
    cart_coord /= length(cart_coord); // normalization
    return vec2(atan2(cart_coord.y,cart_coord.x),atan2(cart_coord.z,length(cart_coord.xy)));
}

vec3 sph2cart(in vec2 sph_coord)
{
    return vec3(sin(sph_coord.x)*cos(sph_coord.y),
    cos(sph_coord.x)*cos(sph_coord.y),
    sin(sph_coord.y));
}

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

    #define NUM_OCTAVES 5

float fbm ( in vec2 _st) {
    float v = 0.0;
    float a = 0.5;
    vec2 shift = vec2(100.0);
    // Rotate to reduce axial bias
    mat2 rot = mat2(cos(0.5), sin(0.5),
    -sin(0.5), cos(0.50));
    for (int i = 0; i < NUM_OCTAVES; ++i) {
        v += a * noise(_st);
        _st = rot * _st * 2.0 + shift;
        a *= 0.5;
    }
    return v;
}

void main() {
//    gl_FragColor = vec4(vec3(fbm(vec2(fbm(v_pos.xy*10.-u_time),fbm(v_pos.zx*10.-u_time)))),1.);
    vec2 uv_pos = cart2sph(v_pos.zxy);
//    vec3 color = vec3(sin((uv_pos.x/PI*2.)*4*PI));
    vec3 color = vec3(sin((v_pos.x/PI*2.+u_time)*4*PI));
    float mask = step(v_pos.z,0.);
    gl_FragColor = vec4(color,1.);
//    gl_FragColor = vec4(vec3(sin((v_pos.x/PI*2.+u_time/2.)*4*PI)),1.);
//    gl_FragColor = vec4(vec3(0.,0.,1.),1.);
}
