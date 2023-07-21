import numpy as np
import cv2 as cv

def readBin(filename):
    with open(filename, 'rb') as f:
        data = np.fromfile(f, dtype=np.uint8)
    return data

a = readBin('D:/Yue Zhang/OneDrive/Bonhoeffer Lab/PycharmProjects/miniPoly/APP/TISCam_compiler/test/20230301_174925'
        '/DMx_22BUC03_33010546_20230301_174925_IC_IMG.miniPoly')

a = a.reshape(-1, 3, 480, 744)
#%%
a = a.flatten().reshape(-1, 480, 744, 3)
b = a[0,:, :, :].sum(axis=2)
# for i in range(1000):
cv.imshow('a', b)
cv.waitKey(0)
cv.destroyAllWindows()

