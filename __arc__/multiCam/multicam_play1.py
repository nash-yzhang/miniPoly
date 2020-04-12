import threading
import Glimgui.tisgrabber.tisgrabber as IC
import cv2 as cv
import ctypes as C
import time as time
import pandas as pd
import numpy as np


def Callback(hGrabber, pBuffer, framenumber, pData):
    if pData.buffer_size > 0:
        image = C.cast(pBuffer, C.POINTER(C.c_ubyte * pData.buffer_size))
        pData.frame = np.ndarray(buffer=image.contents,
                                 dtype=np.uint8,
                                 shape=(pData.height,
                                        pData.width,
                                        pData.iBitsPerPixel))
    else:
        Imageformat = pData.dev_handle.GetImageDescription()[:3]
        pData.width = Imageformat[0]
        pData.height = Imageformat[1]
        pData.iBitsPerPixel = Imageformat[2] // 8
        pData.buffer_size = pData.width * pData.height * pData.iBitsPerPixel

    pData.t = time.time()
    pData.framecount += int(1)
    pData.timeline.append((pData.t, pData.framecount))


class CallbackUserdata(C.Structure):
    def __init__(self, cam_handle):
        self.dev_handle = cam_handle
        self.win = cv.namedWindow(cam_handle.DevName)
        self.width = 0
        self.height = 0
        self.iBitsPerPixel = 0
        self.buffer_size = self.width * self.height * self.iBitsPerPixel
        self.t = time.time()
        self.frame = None
        self.framecount = int(0)
        self.timeline = [(self.t, self.framecount)]


Callbackfunc = IC.TIS_GrabberDLL.FRAMEREADYCALLBACK(Callback)

c1 = IC.TIS_CAM()
c1.DevName = c1.GetDevices()[0].decode("utf-8")
c1.open(c1.DevName)
c1.SetVideoFormat("Y16 (640x480)")
c1.SetFrameRate(30.0)
c1.SetContinuousMode(0)
Userdata1 = CallbackUserdata(c1)
c1.SetFrameReadyCallback(Callbackfunc, Userdata1)

c2 = IC.TIS_CAM()
c2.DevName = c2.GetDevices()[1].decode("utf-8")
c2.open(c2.DevName)
c2.SetVideoFormat("Y16 (640x480)")
c2.SetFrameRate(30.0)
c2.SetContinuousMode(0)
Userdata2 = CallbackUserdata(c2)
c2.SetFrameReadyCallback(Callbackfunc, Userdata2)

#%
# %
def c1loop():
    c1.StartLive(0)
    time.sleep(2.)
    c1.StopLive()


def c2loop():
    c2.StartLive(0)
    time.sleep(2.)
    c2.StopLive()

c1Process = threading.Thread(target=c1loop)
c2Process = threading.Thread(target=c2loop)
c1Process.start()
c2Process.start()
# %%


t1 = pd.DataFrame(Userdata1.timeline)
tidx = pd.Series(np.ones([len(t1)]))
t1 = pd.concat([t1, tidx], axis=1)
t2 = pd.DataFrame(Userdata2.timeline)
t2 = pd.concat([t2, tidx * 2], axis=1)
tt = t1.append(t2)
tt.columns = [0, 1, 2]
tt = tt.sort_values(0)
import matplotlib.pyplot as plt
import matplotlib

matplotlib.use("Qt5Agg")
tt.plot(0, 2)
plt.show()

# c1.SetContinuousMode(0)
# c1.StartLive()
# time.sleep(10.)
# c1.StopLive()
# #%%
# import numpy as np
# 1/np.diff(np.asarray(Userdata.timeline)[:,0])
