import quaternion as qn
import numpy as np
from numpy.fft import fft, ifft

def cart2sph(cxyz):
    # cxy = cx + cy * 1.j
    # azi = np.angle(cxy)
    # elv = np.angle(np.abs(cxy) + cz * 1.j)
    # return azi, elv
    q = qn.qn(cxyz)
    return np.stack([q.u,q.v],axis=-1)

def sph2cart(uvvert):
    return qn.qn(uvvert)['xyz']

def fft_convolve(A, B, dim=0):
    new_dim_order = np.insert(np.delete(np.arange(A.ndim), dim), 0, dim)
    restore_order = np.insert(np.arange(1, A.ndim), new_dim_order[0], 0)
    A = A.transpose(new_dim_order)
    fftB = np.expand_dims(fft(B, axis=0), tuple(np.arange(1, A.ndim)))
    return np.real(ifft(fft(A, axis=0) * fftB, axis=0)).transpose(restore_order)

def rotation2D(theta):
    return np.array([[np.cos(theta), -np.sin(theta)], [np.sin(theta), np.cos(theta)]])

def load_shaderfile(fn):
    with open(fn, 'r') as shaderfile:
        return (shaderfile.read())

def vecNorm(vec, Norm_axis=-1):
    return np.sqrt(np.sum(vec ** 2, Norm_axis))

def vecNormalize(vec, Norm_axis=-1):
    return vec / np.expand_dims(np.sqrt(np.sum(vec ** 2, Norm_axis)), Norm_axis)

def vecAngle(vec1, vec2, Norm_axis=-1):
    v1Norm = vecNorm(vec1, Norm_axis)
    v2Norm = vecNorm(vec2, Norm_axis)
    return np.arccos(np.sum(vec1 * vec2, Norm_axis) / (v1Norm * v2Norm))

def sphAngle(vec, r):
    return np.arcsin(vecNorm(vec[:, np.newaxis, :] - vec[np.newaxis, :, :], 2) / (2 * r)) * 2

def proj_motmat(tileOri, tileCen, motmat):
    tileCen_Q = qn.qn(tileCen)
    tileOri_Q1 = qn.qn(np.real(tileOri)).normalize[:, None]
    tileOri_Q2 = qn.qn(np.imag(tileOri)).normalize[:, None]
    projected_motmat = qn.projection(tileCen_Q[:, None], motmat)
    motmat_out = qn.qdot(tileOri_Q1, projected_motmat) - 1.j * qn.qdot(tileOri_Q2, projected_motmat)
    return motmat_out
