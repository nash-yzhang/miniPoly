// Author @patriciogv ( patriciogonzalezvivo.com ) - 2015

precision highp float;
precision highp int;
uniform vec2 u_resolution;
uniform float u_time;
uniform vec2 st_ang;
uniform vec2 patang;

#define PI 3.14159265358979323846

vec2 rotate2D(vec2 _st, float _angle){
    _st -= 0.5;
    _st =  mat2(cos(_angle),-sin(_angle),
                sin(_angle),cos(_angle)) * _st;
    _st += 0.5;
    return _st;
}

vec2 tile(vec2 _st, float _zoom){
    _st *= _zoom;
    return fract(_st);
}

float box(vec2 _st, vec2 _size, float _smoothEdges){
    _size = vec2(0.5)-_size*0.5;
    vec2 aa = vec2(_smoothEdges*0.5);
    vec2 uv = smoothstep(_size,_size+aa,_st);
    uv *= smoothstep(_size,_size+aa,vec2(1.0)-_st);
    return uv.x*uv.y;
}

void main(void){
//    patang = PI*patang;
    vec2 st = gl_FragCoord.xy/u_resolution.xy+vec2(u_time*sin(2.*PI*st_ang.x),u_time*cos(2.*PI*st_ang.x));
    vec2 st2 =gl_FragCoord.xy/u_resolution.xy+vec2(u_time*sin(2.*PI*st_ang.y),u_time*cos(2.*PI*st_ang.y));
    vec3 color = vec3(0.0);

    // Divide the space in 4
    st = tile(st,9.336);
	st2 = tile(st2,9.336);
    // Use a matrix to rotate the space 45 degrees

    st = rotate2D(st,PI*patang.x);
	st2 = rotate2D(st2,PI*(patang.x+0.356));
    // Draw a square
    color = vec3(box(st,vec2(0.1250,2.50),0.009))+vec3(box(st2,vec2(0.125,2.5),0.010));

    gl_FragColor = vec4(color,1.0);
}
