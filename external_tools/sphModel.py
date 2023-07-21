import warnings
from numpy import pi
import numpy as np
import quaternion as qn
from utils import *
from scipy.spatial import Delaunay


def uv_sphseg(azi_range: tuple, elv_range: tuple, pole_dir=(0, 0, 1), n_azi=30, n_elv=30, coord_type='cart'):
    azi_start, azi_end = azi_range
    elv_start, elv_end = elv_range
    full_elv_arr = np.linspace(elv_start, elv_end, n_elv)
    min_elv = np.ceil(n_azi * np.cos(full_elv_arr[1]))
    uv_vert = []
    for i_elv in full_elv_arr:
        iter_azi = max(np.ceil(n_azi * np.cos(i_elv)), min_elv).astype(int)
        iter_vert = np.empty([iter_azi, 2])
        iter_vert[:, 0] = np.linspace(azi_start, azi_end, iter_azi)
        iter_vert[:, 1] = i_elv
        uv_vert.append(iter_vert)
    uv_face = []
    maxidx = 0
    for i in range(len(uv_vert) - 1):
        iter_vert = np.vstack(uv_vert[i:i + 2])
        iter_tri = Delaunay(iter_vert).simplices + maxidx
        maxidx = sum([len(i) for i in uv_vert[:i + 1]])
        uv_face.append(iter_tri)
    uv_vert = qn.qn(np.vstack(uv_vert))
    rotvec = qn.rotTo(qn.qn((0,0,1)),qn.qn(pole_dir))
    uv_vert = np.squeeze(qn.rotate(rotvec,uv_vert))
    uv_face = np.vstack(uv_face)
    if coord_type.lower() == 'uv':
        return uv_vert.uv, uv_face
    elif coord_type.lower() == 'cart':
        return uv_vert['xyz'], uv_face
    else:
        warningmsg = "Unknown coordinate type: %s, output in cartesian coordinate format" % coord_type
        warnings.warn(warningmsg)
        return uv_vert['xyz'], uv_face


def uv_sphere(max_azi, n_elv):
    elv_arr = np.linspace(-np.pi / 2, np.pi / 2, n_elv)
    min_elv = np.ceil(max_azi * np.cos(elv_arr[1]))
    uv_vert = []
    for i_elv in elv_arr:
        n_azi = max(np.ceil(max_azi * np.cos(i_elv)), min_elv).astype(int)
        iter_vert = np.empty([n_azi, 2])
        iter_vert[:, 0] = np.linspace(-np.pi, np.pi, n_azi)
        iter_vert[:, 1] = i_elv
        uv_vert.append(iter_vert)
    uv_face = []
    maxidx = 0
    for i in range(len(uv_vert) - 1):
        iter_vert = np.vstack(uv_vert[i:i + 2])
        iter_tri = Delaunay(iter_vert).simplices + maxidx
        maxidx = sum([len(i) for i in uv_vert[:i + 1]])
        uv_face.append(iter_tri)
    uv_vert = np.vstack(uv_vert)
    uv_face = np.vstack(uv_face)
    return uv_vert, uv_face


def gen_sphfbm(kernel_sigma: list, n_frame=1000, speed_range=.1, speed_lim=[0, np.inf], uv_pnt=(90, 45)):
    """
    :param kernel_sigma: a list of 3-element array/list/tuple. The first two elements define the
                         spatial/temporal sigma of the gaussian filter. The 3rd elements defines the power.
    :return:
    """

    uv_vert, uv_face = uv_sphere(*uv_pnt)
    q_pnt_full = qn.qn(uv_vert)[..., np.newaxis]
    _, q_pnt_val_idx, q_pnt_val_inv = np.unique(q_pnt_full['xyz'].astype(np.float16), axis=0, return_index=True,
                                                return_inverse=True)
    q_pnt = q_pnt_full[q_pnt_val_idx]
    n_pnt = len(q_pnt_val_idx)
    ang_dist = qn.anglebtw(q_pnt, q_pnt.T)
    gauss_ker = lambda x, sigma: 1 / (sigma * 2 * np.pi) * np.exp(-.5 * (x / sigma) ** 2)
    cumulative_power = 0
    motmat = None
    for i_ker in kernel_sigma:
        q_pnt_val = np.random.randn(3, n_frame, n_pnt)
        q_pnt_val /= np.sqrt(np.sum(q_pnt_val ** 2, axis=0))
        # sp_sig = np.pi / 8
        # tp_sig = 3
        sp_sig = i_ker[0]
        tp_sig = i_ker[1]
        octave_power = i_ker[2]
        cumulative_power += octave_power
        tp_ker = gauss_ker(np.linspace(-int(n_frame / 2), int(n_frame / 2), n_frame), tp_sig)
        tp_ker /= tp_ker.sum()
        q_weight = gauss_ker(ang_dist, sp_sig)
        sp_conv = np.zeros(q_pnt_val.shape)
        for i in range(q_pnt_val.shape[0]):
            sp_conv[i, :, :] = np.dot(np.squeeze(q_pnt_val[i, :, :]), q_weight) / q_weight.sum(axis=0)
        tp_conv = fft_convolve(sp_conv, tp_ker, dim=1)
        full_conv = tp_conv[:, :, q_pnt_val_inv].transpose([1, 2, 0]) * octave_power
        if motmat is not None:
            motmat += np.maximum(np.abs(full_conv), 1.e-07) * np.sign(full_conv)
        else:
            motmat = np.maximum(np.abs(full_conv), 1.e-07) * np.sign(full_conv)
    motmat_sign = np.sign(motmat)
    motmat *= speed_range / np.max(np.abs(motmat))
    motmat = np.minimum(np.maximum(np.abs(motmat), speed_lim[0]), speed_lim[1]) * motmat_sign
    motmat += .5
    return motmat, uv_vert, uv_face


def cylinder(azimuth, height, radius: int = 1, azitile: int = 30, h_tile: int = 8):
    cyl_azi = np.exp(1.j * np.linspace(-azimuth / 2, azimuth / 2, azitile + 1))
    cyl_h = np.linspace(-height / 2, height / 2, h_tile + 1)
    cyl_xy, cyl_h = np.meshgrid(cyl_azi, cyl_h)
    cyl_xy = cyl_xy * radius

    # Vertices positions
    p3 = np.stack((np.real(cyl_xy.flatten()), np.imag(cyl_xy.flatten()), np.real(cyl_h.flatten())), axis=-1)
    # p3 = vecNormalize(p3)
    imgV_conn = np.array([np.arange(azitile) + 1, np.arange(azitile), np.arange(azitile + 1, azitile * 2 + 1, 1),
                          np.arange(azitile + 1, azitile * 2 + 1, 1), np.arange(azitile + 1, azitile * 2 + 1, 1) + 1,
                          np.arange(azitile) + 1]
                         , dtype=np.uint32).T.flatten() + np.array([np.arange(0, h_tile - 1, 1)]).T * (azitile + 1)

    return p3, imgV_conn.reshape(-1, 3)


def tile_param(vertex, faces):
    tile_cen = np.mean(vertex[faces, :], 1)
    tile_sign = np.sign(np.sum(tile_cen * np.cross(vertex[faces[:, 1], :] - vertex[faces[:, 0], :],
                                                   vertex[faces[:, 1], :] - vertex[faces[:, 2], :]), axis=1))
    tile_sign = tile_sign[:, None]
    tileOri = vecNormalize(np.cross(tile_cen, (vertex[faces[:, 1], :] - vertex[faces[:, 0], :]))) + 1.j * vecNormalize(
        (vertex[faces[:, 1], :] - vertex[faces[:, 0], :]))
    return tile_cen, tileOri


def cen2tri(cen_x=np.array([0]), cen_y=np.array([0]), triangle_size=np.array([1])):
    # Assume the triangle will be equal angle ones
    ct1 = [cen_x - triangle_size / 2 * np.sqrt(3), cen_y - triangle_size / 2]
    ct2 = [cen_x + triangle_size / 2 * np.sqrt(3), cen_y - triangle_size / 2]
    ct3 = [cen_x, cen_y + triangle_size / 2 * np.sqrt(3)]
    squarePoint = np.array([ct1, ct2, ct3])
    return squarePoint.transpose([2, 0, 1])


def subdivide_triangle(vertices, faces, subdivide_order):
    subD_faces = faces
    subD_vertices = vertices
    for i in range(subdivide_order):
        edges = np.vstack([np.hstack([subD_faces[:, 0], subD_faces[:, 1], subD_faces[:, 2]]),
                           np.hstack([subD_faces[:, 1], subD_faces[:, 2], subD_faces[:, 0]])]).T
        [edges, inverse_order] = np.unique(np.sort(edges, axis=1), axis=0, return_inverse=True)
        inverse_order = np.reshape(inverse_order, [3, len(subD_faces)]) + len(subD_vertices)
        midPoints = (subD_vertices[edges[:, 0], :] + subD_vertices[edges[:, 1], :]) / 2
        midPoints /= np.array([np.sqrt(np.sum(midPoints ** 2, axis=1))]).T / np.sqrt(np.sum(subD_vertices[0, :] ** 2))
        subD_vertices = np.vstack([subD_vertices, midPoints])
        subD_faces = np.vstack([subD_faces,
                                np.array([subD_faces[:, 0], inverse_order[0, :], inverse_order[2, :]]).T,
                                np.array([subD_faces[:, 1], inverse_order[1, :], inverse_order[0, :]]).T,
                                np.array([subD_faces[:, 2], inverse_order[2, :], inverse_order[1, :]]).T,
                                np.array([inverse_order[0, :], inverse_order[1, :], inverse_order[2, :]]).T])
        # print(len(subD_vertices))
    return subD_vertices, subD_faces


def icoSphere(subdivisionTimes=1):
    r = 1  # (1 + np.sqrt(5)) / 2

    vertices = np.array([
        [-1.0, r, 0.0],
        [1.0, r, 0.0],
        [-1.0, -r, 0.0],
        [1.0, -r, 0.0],
        [0.0, -1.0, r],
        [0.0, 1.0, r],
        [0.0, -1.0, -r],
        [0.0, 1.0, -r],
        [r, 0.0, -1.0],
        [r, 0.0, 1.0],
        [-r, 0.0, -1.0],
        [-r, 0.0, 1.0]
    ])
    vertices /= np.mean(vecNorm(vertices))

    faces = np.array([
        [0, 11, 5],
        [0, 5, 1],
        [0, 1, 7],
        [0, 7, 10],
        [0, 10, 11],
        [1, 5, 9],
        [5, 11, 4],
        [11, 10, 2],
        [10, 7, 6],
        [7, 1, 8],
        [3, 9, 4],
        [3, 4, 2],
        [3, 2, 6],
        [3, 6, 8],
        [3, 8, 9],
        [4, 9, 5],
        [2, 4, 11],
        [6, 2, 10],
        [8, 6, 7],
        [9, 8, 1]
    ])

    [usV, usF] = subdivide_triangle(vertices, faces, subdivisionTimes)

    return usV, usF


def icoSphere4Gl(subdivisionTimes=1):
    usV, usF = icoSphere(subdivisionTimes)
    sphereR = vecNorm(usV[0, :])
    tileCen = np.mean(usV[usF, :], axis=1)
    tileOri = vecNormalize(np.cross(tileCen, usV[usF[:, 1], :] - usV[usF[:, 0], :])) + 1.j * vecNormalize(
        usV[usF[:, 1], :] - usV[usF[:, 0], :])
    tileDist = sphAngle(tileCen, sphereR)
    vtype = [('position', np.float32, 3), ('texcoord', np.float32, 2)]
    usF = np.uint32(usF.flatten())
    Vout = np.zeros(len(usF), vtype)
    Vout['position'] = usV[usF, :]
    Iout = np.arange(usF.size, dtype=np.uint32)

    return Vout, Iout, tileDist, tileCen, tileOri
