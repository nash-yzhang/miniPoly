uniform mat4 u_transformation;// Model matrix
uniform vec3 u_scale;         // scale factor
uniform mat2 u_rotate;         // scale factor
uniform vec2 u_shift;       // 2D translation vector
uniform vec4   u_color;         // Global color

attribute vec4 a_color;         // Vertex color
attribute vec3 a_position;      // Vertex position
varying vec4   v_color;         // Interpolated fragment color (out)
varying vec2   v_texcoord;      // Interpolated fragment texture coordinates (out)
void main()
{
    v_color     = u_color * a_color;
    vec4 t_pos  = u_transformation * vec4(u_scale * a_position,1.0);
    gl_Position = t_pos;
    gl_Position.xy *= u_rotate;
    gl_Position.xy += u_shift*gl_Position.w;
    //gl_Position.z *= 0.;
}



