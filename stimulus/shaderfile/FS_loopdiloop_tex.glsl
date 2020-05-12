uniform sampler2D texture;    // Texture
uniform   vec2 i_texcoord;  // output
varying   vec2 v_texcoord;  // output

void main()
{
    // Final color
    gl_FragColor = texture2D(texture, v_texcoord+i_texcoord);
}