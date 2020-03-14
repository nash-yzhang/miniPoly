from glumpy import app, glm
import numpy as np

# Set up glumpy env
class GPenv:
    def __init__(self, backend = 'pyglet',**kwargs):
        self.backend = backend
        app.use(self.backend)
        self._glWindow = app.Window(**kwargs)
        self._program = {}
        self._buffer = {}  # buffer should be a dictionary

    def prepare_buffer(self):
        # Add your pre-execution script
        pass

    def add_program(self,GPprogram):
        self._program = GPprogram._program
        self._shader = GPprogram._shader


    def on_init(self) :
        # Add your custom on_init script
        self._glWindow.clear (color=(0.0, 0.0, 0.0, 1.0))

    def on_draw(self, dt) :
        # Custom on draw script
        if self.protocol is None :
            return

        self._glWindow.clear (color=(0.0, 0.0, 0.0, 1.0))

        # Call draw
        self.protocol.draw (dt)

    def on_resize(self, width, height) :
        # Custom on resize script
        # Fix for qt5 backend:
        self._glWindow._width = width
        self._glWindow._height = height

        if self.protocol is None :
            return


    def _toggleFullscreen(self):
        if self._glWindow.get_fullscreen() != self._displayConfiguration[madef.DisplayConfig.bool_disp_fullscreen]:
            self._glWindow.set_fullscreen(self._displayConfiguration[madef.DisplayConfig.bool_disp_fullscreen],
                                          screen=self._displayConfiguration[madef.DisplayConfig.int_disp_screen_id])

    def _shutdown(self):
        self._glWindow.close()

    def main(self):
        app.run(framerate=60)

