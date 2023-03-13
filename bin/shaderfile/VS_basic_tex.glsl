attribute vec2   a_pos;         // Screen position
attribute vec2   a_texcoord;    // Texture coordinate
varying   vec2   v_texcoord;   // Interpolated fragment color (out)
void main()
{
    v_texcoord = a_texcoord;
    gl_Position = vec4 (a_pos, 0., 1.);
}