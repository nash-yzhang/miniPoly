attribute vec2 a_pos;
varying vec2 v_pos;
void main () {
    v_pos = a_pos;
    gl_Position = vec4(a_pos, 0.0, 1.0);
}
