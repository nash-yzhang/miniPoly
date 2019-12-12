import numpy
from multiprocessing import Process, Pipe, Lock
from glumpy import app, gl, glm
import time
# -----------------------------------------------------------------------------
# Python and OpenGL for Scientific Visualization
# www.labri.fr/perso/nrougier/python+opengl
# Copyright (c) 2017, Nicolas P. Rougier
# Distributed under the 2-Clause BSD License.
# -----------------------------------------------------------------------------
import numpy as np
from scipy import signal
from glumpy import app, gl, glm, gloo
import cv2 as cv
from sklearn.decomposition import PCA


def cen2square(cen_x=np.array([0]), cen_y=np.array([0]), square_size=np.array([1])):
    square_r = square_size / 2
    squarePoint = np.array([[cen_x - square_r, cen_y - square_r],
                            [cen_x - square_r, cen_y + square_r],
                            [cen_x + square_r, cen_y + square_r],
                            [cen_x + square_r, cen_y - square_r]])
    return squarePoint


def patchArray(imgsize=np.array([1, 1]), startpoint=np.array([[0, 0], [0, 1], [1, 1], [1, 0]])):
    vtype = [('position', np.float32, 2),
             ('texcoord', np.float32, 2)]
    itype = np.uint32
    imgvertice = np.array([np.arange(imgsize[0] + 1)]).T + \
                 np.array([np.arange(imgsize[1] + 1) * 1.j])
    adding_idx = np.arange(imgvertice.size).reshape(imgvertice.shape)

    # Vertices positions
    p = np.stack((np.real(imgvertice.flatten()), \
                  np.imag(imgvertice.flatten())), axis=-1)

    imgV_conn = np.array([[0, 1, imgvertice.shape[1], 1, imgvertice.shape[1], imgvertice.shape[1] + 1]],
                         dtype=np.uint32) + \
                np.array([adding_idx[0:-1, 0:-1].flatten()], dtype=itype).T
    faces_t = np.resize(np.array([1, 0, 2, 0, 2, 3], dtype=itype), imgsize.prod() * 6)
    faces_t += np.repeat(np.arange(imgsize.prod(), dtype=itype) * 4, 6)
    vertices = np.zeros(imgV_conn.size, vtype)
    vertices['position'] = p[imgV_conn.flatten()]
    vertices['texcoord'] = startpoint[faces_t]

    filled = np.arange(imgV_conn.size, dtype=itype)

    vertices = vertices.view(gloo.VertexBuffer)
    filled = filled.view(gloo.IndexBuffer)

    return vertices, filled, faces_t


t = 0
motmat_x_R = np.zeros([100, 100])


def glProcess(conn):
    global t, motmat_x_R
    vertex = """
    uniform mat4   model;      // Model matrix
    uniform mat4   view;       // View matrix
    uniform mat4   projection; // Projection matrix
    attribute vec2 position;   // Vertex position
    attribute vec2 texcoord;   // Vertex texture coordinates red
    varying vec2   v_texcoord;   // Interpolated fragment texture coordinates (out)
    //attribute vec2 texcoord_G;   // Vertex texture coordinates red
    //varying vec2   v_texcoord_G;   // Interpolated fragment texture coordinates (out)
    //attribute vec2 texcoord_B;   // Vertex texture coordinates red
    //varying vec2   v_texcoord_B;   // Interpolated fragment texture coordinates (out)

    void main()
    {
        // Assign varying variables
        v_texcoord  = texcoord;

        // Final position
        gl_Position = projection * view * model * vec4(position,0.0,1.0);
    }
    """

    fragment = """
    uniform sampler2D texture;    // Texture
    varying vec2      v_texcoord; // Interpolated fragment texture coordinates (in)
    void main()
    {
        // Final color
        gl_FragColor = texture2D(texture, v_texcoord);
    }
    """

    t = 0
    app.use("pyglet")
    window = app.Window(width=512, height=512, color=(0, 0, 0, 1))
    # window.set_fullscreen(True)

    keypressed = 0

    @window.event
    def on_draw(dt):
        # from IPython import embed
        # embed()
        window.clear()

        gl.glDisable(gl.GL_BLEND)
        gl.glEnable(gl.GL_DEPTH_TEST)
        # tempsize = int(V['texcoord'].shape[0] / 6)
        # tidx = np.mod(t, 99)
        motmat_ang = conn.recv()
        motmat_x_R = motmat_ang[0]
        motmat_y_R = motmat_ang[1]
        motmat_R = cen2square(np.array([motmat_x_R])[None,:], np.array([motmat_y_R])[None,:], np.array([motmat_y_R])[None,:] * 0).reshape([-1, 2])
        V['texcoord'] += motmat_R[textface] / 300
        # V['texcoord_G'] += motmat_G[textface]/200
        # V['texcoord_B'] += motmat_B[textface]/200
        patchMat.draw(gl.GL_TRIANGLES, I)
        # print(t)

    @window.event
    def on_resize(width, height):
        patchMat['projection'] = glm.perspective(45.0, width / float(height), 2.0, 100.0)

    @window.event
    def on_init():
        gl.glEnable(gl.GL_DEPTH_TEST)

    patchArray_size = np.array([1, 1])
    startpoint = cen2square(np.random.rand(patchArray_size.prod()),
                            np.random.rand(patchArray_size.prod()),
                            np.ones(patchArray_size.prod()) / 10).reshape([-1, 2])
    # first build the smoothing kernel
    sigma = np.array([1, 1, 5]) / 2  # width of kernel
    x = np.linspace(-10, 10, 50)  # coordinate arrays -- make sure they contain 0!
    y = np.linspace(-10, 10, 50)
    z = np.linspace(-10, 10, 50)
    xx, yy, zz = np.meshgrid(x, y, z)
    kernel = np.exp(-(xx ** 2 / (2 * sigma[0] ** 2) + yy ** 2 / (2 * sigma[1] ** 2) + zz ** 2 / (2 * sigma[2] ** 2)))
    motmat_ang = [1,0]
    motmat_x_R = motmat_ang[0]
    motmat_y_R = motmat_ang[1]
    # motmat_angle_R = np.exp(np.random.rand(*patchArray_size, 100) * 2.j * np.pi)
    # motmat_x_R = signal.convolve(motmat_angle_R.real, kernel, mode='same').reshape(patchArray_size.prod(), -1)
    # motmat_y_R = signal.convolve(motmat_angle_R.imag, kernel, mode='same').reshape(patchArray_size.prod(), -1)
    V, I, textface = patchArray(patchArray_size, startpoint)
    patchMat = gloo.Program(vertex, fragment)
    patchMat.bind(V)
    patchMat['texture'] = np.uint8(np.round((np.random.rand(100, 100, 1) > .5) * 155 + 100) * np.array([[[1, 1, 1]]]))
    patchMat['texture'].wrapping = gl.GL_REPEAT
    patchMat['model'] = np.eye(4, dtype=np.float32)
    patchMat['view'] = glm.translation(*patchArray_size * -.5, -2)
    app.run(framerate=60)

import os
fdir = 'MappApp/output_2019-12-11-14-31-13.avi'

def cvProcess(conn):
    global fdir
    pca = PCA(n_components=2)
    vobj = cv.VideoCapture(fdir)
    xbound = [10, -50]
    ybound = [10, -10]
    sizebound = [50, 300]
    t1 = time.time()
    for k in range(2000):
        # print(fdir)
        # print(k)
        # print(type(vobj.read()[1]))
        rawim = vobj.read()[1]
        t1 = time.time()
        imslice = rawim[xbound[0]:xbound[1], ybound[0]:ybound[1], 0]
        th2 = 255 - cv.adaptiveThreshold(imslice, 255, cv.ADAPTIVE_THRESH_GAUSSIAN_C, cv.THRESH_BINARY, 201, 10)
        _, labels = cv.connectedComponents(th2)
        labelC = np.bincount(labels.flatten())
        idx = [i for i, x in enumerate(labelC) if ((x > sizebound[0]) & (x <= sizebound[1]))]
        if len(idx) > 0:
            th3 = (labels == idx[0])
        fx, fy = np.where(th3)
        f = np.vstack([fx, fy]).T
        if len(f) > 0:
            pca.fit(f)
            cenpoint = np.mean(f, axis=0)
            tempscore = np.sum(pca.components_[0, :] * (f - np.mean(f, axis=0)), axis=1)
            p1 = f[np.argmin(tempscore), ::-1]
            p2 = f[np.argmax(tempscore), ::-1]
            cenpoint = [int(cenpoint[0] + xbound[0]), int(cenpoint[1] + ybound[0])]
            # if k>2:
            xbound = [max(cenpoint[0] - 40, 0), min(cenpoint[0] + 40, rawim.shape[0])]
            ybound = [max(cenpoint[1] - 40, 0), min(cenpoint[1] + 40, rawim.shape[1])]
            ang1 = p2-p1
            ang1 = ang1/np.sqrt(np.sum(ang1**2))
            conn.send(ang1)
            res = max(1./60+t1-time.time(),1e-6)
            time.sleep(res)
        else:
            print("nan")



if __name__ == '__main__':
    os.chdir('/home/yue/PycharmProjects/')
    lock = Lock()
    receiver,sender = Pipe()
    p1 = Process(target=cvProcess, args=(sender,))
    p2 = Process(target=glProcess, args=(receiver,))
    p1.start()
    p2.start()
    p1.join()
    p2.join()

# %%
