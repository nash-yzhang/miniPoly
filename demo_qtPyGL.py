# from bin.minion import BaseMinion,LoggerMinion
# import logging,sys
# from vispy import app
# import vispy
# import PyQt5.QtWidgets as qw
# from bin.GUI import BaseGUI
# from bin.Display import GLDisplay
from bin.app import GLapp

# class GUI(BaseMinion):
#     def __init__(self,*args,**kwargs):
#         super(GUI, self).__init__(*args,**kwargs)
#
#     def main(self):
#         app = qw.QApplication(sys.argv)
#         w = BaseGUI(self, rendererName='renderer/planeAnimator.py', )
#         self.log(logging.INFO,"Starting GUI")
#         w.show()
#         app.exec()
#         self.shutdown()
#
#     def shutdown(self):
#         for tgt in self.target.keys():
#             while self.get_state(tgt, "status") != -1:
#                 self.set_state(tgt, "status", -1)
#         self.set_state(self.name, "status", -1)


# class GLCanvas(gp.glCanvas):
#     def __init__(self,handler,*args,**kwargs):
#         super(GLCanvas, self).__init__(*args,**kwargs)
#         self._processHandler = handler
#         self._setTime = 0
#         self._tic = 0
#         self._rmtShutdown = False
#
#     def on_timer(self, event):
#         if self.timer.elapsed - self._setTime > 1:
#             self._setTime = np.floor(self.timer.elapsed)
#             msg = self._processHandler.get('Controller')
#             if msg is not None:
#                 if msg[0] == 'rendering_script':
#                     self._renderer_path = msg[1]
#                     self.rendererName = self._renderer_path.split("/")[-1][:-3]
#                     self._processHandler.log(logging.INFO,"Received rendering script [{}] from [Controller]".format(self._renderer_path))
#                     self.importModuleFromPath()
#                     self._renderer = self.imported.Renderer(self)
#                     self.load(self._renderer)
#                     self._processHandler.log(logging.INFO,"Running script [{}]".format(self._renderer_path))
#         self.update()
#         if self._processHandler.get_state()==-1:
#             self._rmtShutdown = True
#             self.on_close()
#         elif self._processHandler.get_state()== 0:
#             self.on_close()
#
#     def on_close(self):
#         if not self._rmtShutdown:
#             self._processHandler.set_state(self._processHandler.name,'status',0)
#         self.close()
#
#     def importModuleFromPath(self):
#         spec = util.spec_from_file_location(self.rendererName, location=self._renderer_path)
#         self.imported = util.module_from_spec(spec)
#         sys.modules[self.rendererName] = self.imported
#         spec.loader.exec_module(self.imported)
#
# class CanvasHandler(BaseMinion):
#     def main(self):
#         try:
#             vispy.use('glfw')
#             cvs = GLDisplay(self)
#             cvs.show()
#             app.run()
#             cvs.on_close()
#         except Exception:
#             self.error(Exception)



if __name__ == "__main__":
    app = GLapp("main")
    app.run()
    # lm = LoggerMinion()
    # gui = GUI('Controller')
    # canvas = CanvasHandler('Display')
    # gui.attach_logger(lm)
    # canvas.attach_logger(lm)
    # gui.add_target(canvas)
    # gui.run()
    # canvas.run()
    # lm.run()
