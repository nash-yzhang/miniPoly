# -*- coding: utf-8 -*-
import numpy as np
import ctypes
import imgui
from vispy import app,gloo
import logging

#---------- Copied from glumpy.log ----------#
log = logging.getLogger('vispy')
log.setLevel(logging.INFO)
# create console handler and set level to debug
ch = logging.StreamHandler()
# create formatter
# formatter = logging.Formatter('%(levelname)s: %(message)s')
# formatter = logging.Formatter('%(message)s')
class Formatter(logging.Formatter):
    def format(self, record):
        prefix = {logging.INFO    : "[i]",
                  logging.WARNING : "[w]",
                  logging.ERROR   : "[e]",
                  logging.CRITICAL: "[x]"}
        if record.levelno in (
                logging.INFO,
                logging.WARNING,
                logging.ERROR,
                logging.CRITICAL):
            record.msg = '%s %s' % (prefix[record.levelno], record.msg)
        return super(Formatter , self).format(record)
formatter = Formatter('%(message)s')
#---------- Copied from glumpy.log ----------#


# add formatter to ch
ch.setFormatter(formatter)

# add ch to logger
log.addHandler(ch)

VERTEX_SHADER_SRC = """
#version 330
uniform mat4 ProjMtx;
in vec2 Position;
in vec2 UV;
in vec4 Color;
out vec2 Frag_UV;
out vec4 Frag_Color;
void main() {
    Frag_UV = UV;
    Frag_Color = Color;
    gl_Position = ProjMtx * vec4(Position.xy, 0, 1);
}
"""

FRAGMENT_SHADER_SRC = """
#version 330
uniform sampler2D Texture;
in vec2 Frag_UV;
in vec4 Frag_Color;
out vec4 Out_Color;
void main() {
    vec4 col = Frag_Color; //original
    Out_Color = col * texture(Texture, Frag_UV.st); //original

}
"""

io = None
prog: gloo.Program = None


class VispyRenderer(app.Canvas):
    """Vispy backend for pyimgui. The code is directly modified from the glumpy integration, include this comment. """

    def __init__(self,*args,**kwargs):

        # self.io is initialized by super-class
        if not imgui.get_current_context():
            raise RuntimeError(
                "No valid ImGui context. Use imgui.create_context() first and/or "
                "imgui.set_current_context()."
            )
        app.Canvas.__init__(self,*args,**kwargs,shared=imgui.get_current_context())
        self.io = imgui.get_io()

        # if attach_callbacks:
        #     glfw.set_key_callback(self.window, self.keyboard_callback)
        #     glfw.set_cursor_pos_callback(self.window, self.mouse_callback)
        #     glfw.set_window_size_callback(self.window, self.resize_callback)
        #     glfw.set_char_callback(self.window, self.char_callback)
        #     glfw.set_scroll_callback(self.window, self.scroll_callback)

        self.io.display_size = self.size
        self._gui_time = None

    def _create_device_objects(self):
        self.prog = gloo.Program(self.VERTEX_SHADER_SRC, self.FRAGMENT_SHADER_SRC)

    def render(self, draw_data):

        # perf: local for faster access
        io = self.io

        display_width, display_height = io.display_size
        fb_width = int(display_width * io.display_fb_scale[0])
        fb_height = int(display_height * io.display_fb_scale[1])

        if fb_width == 0 or fb_height == 0:
            return

        draw_data.scale_clip_rects(*io.display_fb_scale)

        ortho_projection = (ctypes.c_float * 16)(
            2.0 / display_width, 0.0, 0.0, 0.0,
            0.0, 2.0 / -display_height, 0.0, 0.0,
            0.0, 0.0, -1.0, 0.0,
            -1.0, 1.0, 0.0, 1.0
        )

        self.prog["ProjMtx"] = ortho_projection

        for commands in draw_data.commands_lists:
            for command in commands.commands:
                # TODO: ImGui Images will not work yet, homogenizing texture id
                # allocation by imgui/glumpy is likely a larger issue
                #
                # accessing command.texture_id crashes the prog
                #
                # GL.glBindTexture(GL.GL_TEXTURE_2D, command.texture_id )

                x, y, z, w = command.clip_rect
                gloo.set_scissor(int(x), int(fb_height - w), int(z - x), int(w - y))

                idx_array = idx_content[idx_buffer_offset:(idx_buffer_offset + command.elem_count)].view(
                    gloo.IndexBuffer)
                self.prog.draw('triangles', indices=idx_array)

                idx_buffer_offset += command.elem_count

        # restore modified GL state
        GL.glUseProgram(last_program)
        GL.glActiveTexture(last_active_texture)
        GL.glBindTexture(GL.GL_TEXTURE_2D, last_texture)
        GL.glBindVertexArray(last_vertex_array)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, last_array_buffer)
        GL.glBindBuffer(GL.GL_ELEMENT_ARRAY_BUFFER, last_element_array_buffer)
        GL.glBlendEquationSeparate(last_blend_equation_rgb, last_blend_equation_alpha)
        GL.glBlendFunc(last_blend_src, last_blend_dst)

        if last_enable_blend:
            GL.glEnable(GL.GL_BLEND)
        else:
            GL.glDisable(GL.GL_BLEND)

        if last_enable_cull_face:
            GL.glEnable(GL.GL_CULL_FACE)
        else:
            GL.glDisable(GL.GL_CULL_FACE)

        if last_enable_depth_test:
            GL.glEnable(GL.GL_DEPTH_TEST)
        else:
            GL.glDisable(GL.GL_DEPTH_TEST)

        if last_enable_scissor_test:
            GL.glEnable(GL.GL_SCISSOR_TEST)
        else:
            GL.glDisable(GL.GL_SCISSOR_TEST)

        GL.glViewport(last_viewport[0], last_viewport[1], last_viewport[2], last_viewport[3])
        GL.glScissor(last_scissor_box[0], last_scissor_box[1], last_scissor_box[2], last_scissor_box[3])

        log.debug("----------------------end---------------------------------")

    def _invalidate_device_objects(self):
        pass
