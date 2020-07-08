from matplotlib import pyplot as plt
# import matplotlib
import time
import numpy as np
import cv2 as cv
from sklearn.decomposition import PCA
from scipy.ndimage import rotate
#
#%%
pca = PCA(n_components=2)
def vec_to_C(vec):
    return vec[0]+1.j*vec[1]
def C_to_vec(complex_num):
    return np.array([complex_num.real,complex_num.imag])
def rotMat(angle):
    return np.array([[np.cos(angle),-np.sin(angle)],[np.sin(angle),np.cos(angle)]])
def anglebtw(vec1,vec2):
    vec1c = vec_to_C(vec1)
    vec1c /= np.abs(vec1c)
    vec2c = vec_to_C(vec2)
    vec2c /= np.abs(vec2c)
    return (np.log(vec1c/vec2c)).imag
def pix_mean(bwim):
    return np.array(np.where(bwim)).mean(axis = 1)

def longaxis(bwim):
    pix_x, pix_y = np.where(bwim)
    pix_coord = np.vstack([pix_x, pix_y]).T
    pca.fit(pix_coord)
    cenpoint = np.mean(pix_coord, axis=0)
    body_axis_vector = pca.components_[0, :]
    body_axis_score = np.sum(body_axis_vector * (pix_coord - cenpoint), axis=1)
    head = cenpoint[::-1]+np.max(body_axis_score)*body_axis_vector[::-1]
    tail = cenpoint[::-1]+np.min(body_axis_score)*body_axis_vector[::-1]

    # head = pix_coord[np.argmin(body_axis_score), ::-1]
    # tail = pix_coord[np.argmax(body_axis_score), ::-1]
    return np.vstack([head,tail])

vobj = cv.VideoCapture("output_2019-12-11-14-24-51.avi")
ybound = np.array([100,600])
xbound = np.array([0,500])
sizebound = [50,300]
eyesize = 12
t = time.time()
startframe = 1
endframe = 173
fig = plt.figure(1)
fig.clf()
ax2 = plt.axes()#fig.add_subplot(3,1,1)
ax2.set_aspect('equal', 'box')
plt.axis('off')
# ax1 = plt.axes([0.74, 0.64, 0.2, 0.2])#fig.add_subplot(3,1,[2,3])
# plt.axis('off')
fig.canvas.draw()
ax2background = fig.canvas.copy_from_bbox(ax2.bbox)
# axbackground = fig.canvas.copy_from_bbox(ax1.bbox)
rawim = vobj.read()[1]
imslice = rawim[xbound[0]:xbound[1],ybound[0]:ybound[1],0]
plt.imshow(imslice)
#%%
body_axis = np.array([[0,0],[0,0]])
t = time.time ()
# for k in range(1,endframe,1):
while True:
    rawim = vobj.read()[1]
    # if not rawim
    imslice = rawim[xbound[0]:xbound[1],ybound[0]:ybound[1],0]
    try:
        th2 = 255 - cv.adaptiveThreshold(imslice, 255, cv.ADAPTIVE_THRESH_MEAN_C, cv.THRESH_BINARY, 21, 15)
        _, labels = cv.connectedComponents(th2)
        labelC = np.bincount(labels.flatten())
        sizebound = [40, 100]
        idx = [i for i, x in enumerate(labelC) if ((x > sizebound[0]) & (x <= sizebound[1]))]
        th3 = np.isin(labels, idx)
        body_axis = longaxis(th3)
        botheye = np.round(body_axis).astype(np.int)
        validsize = labelC[(labelC > sizebound[0]) & (labelC <= sizebound[1])]
    except:
        pass
    angCorr = -anglebtw([0, -1], body_axis[1] - body_axis[0])
    xbound = np.array([max(min(botheye[:,1]) - 80+xbound[0], 0), min(max(botheye[:,1]) + 80+xbound[0], rawim.shape[1])])
    ybound = np.array([max(min(botheye[:,0]) - 80+ybound[0], 0), min(max(botheye[:,0]) + 80+ybound[0], rawim.shape[0])])
    sizebound =[min(validsize)-40, max(validsize)+40]
    loc_cor = [ybound[0],xbound[0]]
    annotated = cv.line(rawim,tuple(botheye[0]+loc_cor),tuple(botheye[1]+loc_cor),(255,0,0),thickness=2)
    try:
        # img.set_data(rotate(imslice,angCorr/np.pi*180,reshape=False))
        imgfull.set_data(annotated)
        # baLine[0].set_data(*(body_axis+np.array([ybound[0],xbound[0]])).T)
        # fig.canvas.restore_region(axbackground)
        fig.canvas.restore_region(ax2background)

        # redraw just the points
        # ax1.draw_artist(img)
        ax2.draw_artist(imgfull)
        # ax2.draw_artist(baLine[0])
        # fill in the axes rectangle
        fig.canvas.blit(ax2.bbox)
        # fig.canvas.blit(ax1.bbox)
        fig.canvas.flush_events()
        plt.pause(.001)
    except:
        # img = ax1.imshow(rotate(imslice, angCorr / np.pi * 180, reshape=False), cmap='gray', interpolation="None")
        imgfull = ax2.imshow(annotated, cmap='gray', interpolation="None")
        # baLine = ax2.plot(*body_axis.T, 'r')


    # -1:
print('%.4f'%((time.time() - t)/endframe))




        #%%