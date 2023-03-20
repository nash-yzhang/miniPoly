from bin.widgets.prototypes import AbstractAPP
from bin.compiler import TISCameraCompiler


class TisCamApp(AbstractAPP):
    def __init__(self, *args, camera_name=None, save_option='binary', **kwargs):
        super(TisCamApp, self).__init__(*args, **kwargs)
        self._param_to_compiler['camera_name'] = camera_name
        self._param_to_compiler['save_option'] = save_option

    def initialize(self):
        super().initialize()
        self._compiler = TISCameraCompiler(self, **self._param_to_compiler, )
        self.info("Camera Interface initialized.")
