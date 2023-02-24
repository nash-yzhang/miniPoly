"""
Created on Fri Aug 9 10:11:32 2019
Last update: Fri Nov 8 17:14:32 2019
@author: Yue Zhang
"""
import numpy as np
import warnings


class qn (np.ndarray) :

    qn_dtype = [('w', np.double), ('x', np.double), ('y', np.double), ('z', np.double)]

    def __new__(cls, compact_mat):
        """
        Override the __new__ function of ndarray for generating new instance of quaternion array
        ----------------------------------
        :param compact_mat: M x ... x N x 4 ndarray or list. The slices of the last dimension will be assigned as the 4 parts of quaternion. If the last dimension of the input array only have 3 slices, then the input
                                array is assumed to be the coordinates of 3D cartesian space, the slices in
                                such an array will be assigned the field x, y, z respectively, the field w
                                will be filled with 0. A warning message will be returned to remind the
                                assumption of the input data structure.
        :return: M x ... x N quaternion structured array.
        """
        mattype = type(compact_mat)
        if mattype == list or mattype == tuple :  # Check if input is ndarray or list, else return uv_facet type error
            compact_mat = np.asarray(compact_mat)
        elif mattype == np.ndarray:
            pass
        else:
            raise Exception('Input array should be list or ndarray, instead its type is %s\n' % mattype)
        matshape = compact_mat.shape  # Shape checking: should be M x ... x 4 or x 3 ndarray, otherwise return error
        qn_compact = np.zeros([*matshape[:-1]], dtype=qn.qn_dtype)  # Preallocate space
        qn_compact = np.full_like(qn_compact, np.nan)  # filled with nan for debugging.
        if matshape[-1] == 4:
            compact_mat_r = compact_mat.reshape([-1, 4])
            qn_compact['w'] = compact_mat_r[:, 0].reshape(matshape[:-1])
            qn_compact['x'] = compact_mat_r[:, 1].reshape(matshape[:-1])
            qn_compact['y'] = compact_mat_r[:, 2].reshape(matshape[:-1])
            qn_compact['z'] = compact_mat_r[:, 3].reshape(matshape[:-1])
        elif matshape[-1] == 3:
            targetshape = list(matshape)
            targetshape[-1] = 4
            compact_mat_r = compact_mat.reshape([-1, 3])
            qn_compact['w'] = np.zeros(matshape[:-1])
            qn_compact['x'] = compact_mat_r[:, 0].reshape(matshape[:-1])
            qn_compact['y'] = compact_mat_r[:, 1].reshape(matshape[:-1])
            qn_compact['z'] = compact_mat_r[:, 2].reshape(matshape[:-1])
            warningmsg = "Input array %s is set to %s" % (matshape, tuple(targetshape))
            warnings.warn(warningmsg)
        elif matshape[-1] == 2:
            targetshape = list(matshape)
            targetshape[-1] = 4
            compact_mat_r = compact_mat.reshape([-1, 2])
            compact_mat_xy = np.exp(1j * compact_mat_r[:, 0]) * np.cos(compact_mat_r[:, 1])
            compact_mat_z = np.sin(compact_mat_r[:, 1])
            qn_compact['w'] = np.zeros(matshape[:-1])
            qn_compact['x'] = np.real(compact_mat_xy).reshape(matshape[:-1])
            qn_compact['y'] = np.imag(compact_mat_xy).reshape(matshape[:-1])
            qn_compact['z'] = compact_mat_z.reshape(matshape[:-1])
            warningmsg = "Input array %s is set to %s" % (matshape, tuple(targetshape))
            warnings.warn(warningmsg)
        else:
            raise Exception('Input array should be uv_facet N x ... x 4 matrix, instead its shape is %s\n' % (matshape,))
        obj = qn_compact.view(cls)  # Convert to quaternion ndarray object
        if obj.shape == ():  # Convert 1 element array (has 0 dim) to 1-d array
            obj = np.expand_dims(obj, -1)
        return obj

    ###################################  Method  ###################################

    def __getitem__(self, keys):
        """
        Custom indexing for structured quaternion ndarray
        """
        sub_self = self.view(np.ndarray)
        if type(keys) == int:  # If index is integer, converted to slices; otherwise cause error
            keys = slice(keys, keys + 1)
            sub_self = sub_self[keys]
            return sub_self.view(qn)

        if type(keys) == str:
            concat = np.concatenate([sub_self[i][...,np.newaxis] for i in keys],axis=-1)
            if concat.shape[-1] == 1:
                concat = concat[...,0]
            return concat

        else:
            return sub_self[keys].view(qn)

    def __repr__(self):
        """
        Custom representation for the quaternion array. each quaternion number will be
        show as "a+bi+cj+dk". The printed string are organized in the same way
        as the quaternion ndarray
        """
        concate_q_array = self.compact
        string_array = []
        for ci in range(concate_q_array.shape[0]):
            string_array.append("%+.4g%+.4gi%+.4gj%+.4gk" % tuple(concate_q_array[ci, :]))
        string_output = np.array2string(np.asarray(string_array).reshape(self['w'].shape))
        if len(string_output) > 1000 // 4 * 4:
            string_output = string_output[:1000 // 4 * 4] + '...'

        return '\n'.join(["Quaternion Array " + str(self.shape) + ": ", string_output])

    def __neg__(self):
        # Elementary arithmetic: qn * -1
        compact_product = -self.matrixform
        return np.reshape(compact_product.view(self.qn_dtype).view(qn), compact_product.shape[:-1])

    def __add__(self, qn2):
        # Elementary arithmetic: qn1 + qn2 or qn1 + r (real number). Same as the elementary arithmetic for real number
        if any([1 if (qn2.__class__ == k) else 0 for k in (int, float, np.ndarray, np.float64, np.float32, np.int)]):
            compact_product = np.concatenate([self['w']+qn2,self['xyz']],-1)
        elif qn2.__class__ == self.__class__:
            compact_product = self.matrixform + qn2.matrixform
        else:
            raise ValueError('Invalid type of input')
        return np.reshape(compact_product.view(self.qn_dtype).view(qn), compact_product.shape[:-1])

    def __iadd__(self, qn2):
        # Elementary arithmetic: qn1 += qn2 or qn1 += r
        return self.__add__(qn2)

    def __radd__(self, qn2):
        # Elementary arithmetic: qn2 + qn1 or r + qn1
        return self.__add__(qn2)

    def __sub__(self, qn2):
        # Elementary arithmetic: qn1 - qn2. Same as the elementary arithmetic for real number
        if any([1 if (qn2.__class__ == k) else 0 for k in (int, float, np.ndarray, np.float64, np.float32, np.int)]):
            compact_product = self.matrixform - qn2
        elif qn2.__class__ == qn:
            compact_product = self.matrixform - qn2.matrixform
        else:
            raise ValueError('Invalid type of input')
        return np.reshape(compact_product.view(self.qn_dtype).view(qn), compact_product.shape[:-1])

    def __isub__(self, qn2):
        # Elementary arithmetic: qn1 -= qn2 or qn1 -= r
        return self.__sub__(qn2)

    def __rsub__(self, qn2):
        # Elementary arithmetic: qn2 - qn1 or r - qn1
        if any([1 if (qn2.__class__ == k) else 0 for k in (int, float, np.ndarray, np.float64, np.float32, np.int)]):
            compact_product = qn2 - self.matrixform
        elif qn2.__class__ == qn:
            compact_product = qn2.matrixform - self.matrixform
        else:
            raise ValueError('Invalid type of input')
        return np.reshape(compact_product.view(self.qn_dtype).view(qn), compact_product.shape[:-1])

    def __mul__(self, qn2):
        # Elementary arithmetic: qn1 * qn2; check https://en.wikipedia.org/wiki/Quaternion#Algebraic_properties for
        # details
        if any([1 if (qn2.__class__ == k) else 0 for k in (int, float, np.ndarray, np.float64, np.float32, np.int)]):
            # if qn1 * r, then the same as real number calculation
            compact_product = self.matrixform * qn2
            compact_product = np.reshape(compact_product.view(self.qn_dtype), compact_product.shape[:-1])
        elif qn2.__class__ == self.__class__:
            temp_shape = (self['w'] * qn2['w']).shape
            if not temp_shape:
                compact_product = np.zeros([(self['w'] * qn2['w']).size], dtype=self.qn_dtype)
            else:
                compact_product = np.zeros([*temp_shape], dtype=self.qn_dtype)
            compact_product = np.full_like(compact_product, np.nan)
            compact_product['w'] = self['w'] * qn2['w'] - self['x'] * qn2['x'] - self['y'] * qn2['y'] - self['z'] * qn2[
                'z']
            compact_product['x'] = self['w'] * qn2['x'] + self['x'] * qn2['w'] + self['y'] * qn2['z'] - self['z'] * qn2[
                'y']
            compact_product['y'] = self['w'] * qn2['y'] - self['x'] * qn2['z'] + self['y'] * qn2['w'] + self['z'] * qn2[
                'x']
            compact_product['z'] = self['w'] * qn2['z'] + self['x'] * qn2['y'] - self['y'] * qn2['x'] + self['z'] * qn2[
                'w']
        else:
            raise ValueError('Invalid type of input')
        return compact_product.view(qn)

    def __rmul__(self, qn2):
        # Elementary arithmetic: qn2 * qn1; Note the result of _rmul_ and _mul_ are not equal for quaternion
        if any([1 if (qn2.__class__ == k) else 0 for k in (int, float, np.ndarray, np.float64, np.float32, np.int)]):
            compact_product = self.matrixform * qn2
            compact_product = np.reshape(compact_product.view(self.qn_dtype), compact_product.shape[:-1])
        elif qn2.__class__ == self.__class__:
            temp_shape = (self['w'] * qn2['w']).shape
            if not temp_shape:
                compact_product = np.zeros([(self['w'] * qn2['w']).size], dtype=self.qn_dtype)
            else:
                compact_product = np.zeros([*temp_shape], dtype=self.qn_dtype)
            compact_product = np.full_like(compact_product, np.nan)
            compact_product['w'] = qn2['w'] * self['w'] - qn2['x'] * self['x'] - qn2['y'] * self['y'] - qn2['z'] * self[
                'z']
            compact_product['x'] = qn2['w'] * self['x'] + qn2['x'] * self['w'] + qn2['y'] * self['z'] - qn2['z'] * self[
                'y']
            compact_product['y'] = qn2['w'] * self['y'] - qn2['x'] * self['z'] + qn2['y'] * self['w'] + qn2['z'] * self[
                'x']
            compact_product['z'] = qn2['w'] * self['z'] + qn2['x'] * self['y'] - qn2['y'] * self['x'] + qn2['z'] * self[
                'w']
        else:
            raise ValueError('Invalid type of input')
        return compact_product.view(qn)

    def __imul__(self, qn2):
        # Elementary arithmetic: qn1 *= qn2; check https://en.wikipedia.org/wiki/Quaternion#Algebraic_properties for
        # details
        return self.__mul__(qn2)

    def __truediv__(self, qn2):
        # Elementary arithmetic: qn1 / qn2; Note the result of __truediv__ and __rtruediv__ are not equal for quaternion
        if any([1 if (qn2.__class__ == k) else 0 for k in (int, float, np.float64, np.float32, np.int)]):
            compact_product = self.matrixform / qn2
            compact_product = np.reshape(compact_product.view(self.qn_dtype), compact_product.shape[:-1])
        elif qn2.__class__ == np.ndarray:
            compact_product = self.matrixform / qn2[..., None]
            compact_product = np.reshape(compact_product.view(self.qn_dtype), compact_product.shape[:-1])
        elif qn2.__class__ == self.__class__:
            inv_qn2 = qn2.inv
            temp_shape = (self['w'] * inv_qn2['w']).shape
            if not temp_shape:
                compact_product = np.zeros([(self['w'] * inv_qn2['w']).size], dtype=self.qn_dtype)
            else:
                compact_product = np.zeros([*temp_shape], dtype=self.qn_dtype)
            compact_product = np.full_like(compact_product, np.nan)
            compact_product['w'] = self['w'] * inv_qn2['w'] - self['x'] * inv_qn2['x'] - self['y'] * inv_qn2['y'] - self[
                'z'] * inv_qn2['z']
            compact_product['x'] = self['w'] * inv_qn2['x'] + self['x'] * inv_qn2['w'] + self['y'] * inv_qn2['z'] - self[
                'z'] * inv_qn2['y']
            compact_product['y'] = self['w'] * inv_qn2['y'] - self['x'] * inv_qn2['z'] + self['y'] * inv_qn2['w'] + self[
                'z'] * inv_qn2['x']
            compact_product['z'] = self['w'] * inv_qn2['z'] + self['x'] * inv_qn2['y'] - self['y'] * inv_qn2['x'] + self[
                'z'] * inv_qn2['w']
        else:
            raise ValueError('Invalid type of input')
        return compact_product.view(qn)

    def __rtruediv__(self, qn2):
        """
        Elementary arithmetic: qn2 / qn1; Note the result of __truediv__ and __rtruediv__ are not equal for quaternion

        :param qn2: quaternion or real number ndarray
        :return: quaternion ndarray; qn2 / qn1
        """
        inv_self: qn = self.inv
        if any([1 if (qn2.__class__ == k) else 0 for k in (int, float, np.float64, np.float32, np.int)]):
            compact_product = inv_self.matrixform / qn2
            compact_product = np.reshape(compact_product.view(self.qn_dtype), compact_product.shape[:-1])
        elif qn2.__class__ == np.ndarray:
            compact_product = inv_self.matrixform / qn2[..., None]
            compact_product = np.reshape(compact_product.view(self.qn_dtype), compact_product.shape[:-1])
        elif qn2.__class__ == self.__class__:
            temp_shape = (qn2['w'] * inv_self['w']).shape
            if not temp_shape:
                compact_product = np.zeros([(qn2['w'] * inv_self['w']).size], dtype=self.qn_dtype)
            else:
                compact_product = np.zeros([*temp_shape], dtype=self.qn_dtype)
            compact_product = np.full_like(compact_product, np.nan)
            compact_product['w'] = qn2['w'] * inv_self['w'] - qn2['x'] * inv_self['x'] - qn2['y'] * inv_self['y'] - qn2[
                'z'] * inv_self['z']
            compact_product['x'] = qn2['w'] * inv_self['x'] + qn2['x'] * inv_self['w'] + qn2['y'] * inv_self['z'] - qn2[
                'z'] * inv_self['y']
            compact_product['y'] = qn2['w'] * inv_self['y'] - qn2['x'] * inv_self['z'] + qn2['y'] * inv_self['w'] + qn2[
                'z'] * inv_self['x']
            compact_product['z'] = qn2['w'] * inv_self['z'] + qn2['x'] * inv_self['y'] - qn2['y'] * inv_self['x'] + qn2[
                'z'] * inv_self['w']
        else:
            raise ValueError('Invalid type of input')
        return compact_product.view(qn)

    def __itruediv__(self, qn2):
        """
        Elementary arithmetic: qn1 /= qn2 (or real number);

        :param qn2: quaternion or real number ndarray
        :return: quaternion ndarray;
        """
        # Elementary arithmetic:
        return self.__truediv__(qn2)

    ########### Properties ###########
    @property
    def matrixform(self):
        """
        Converted to the double M x ... x 4 unstructured ndarray

        :return:  M x ... x 4 ndarray
        """
        return self['wxyz']

    @property
    def compact(self):
        """
        Converted to double (Mx...xN) x 4 unstructured ndarray

        :return:  (Mx...xN) x 4 ndarray
        """
        #
        return self.matrixform.reshape(-1, 4)

    @property
    def conj(self):
        """
        Conjugate: conj(a+bi+cj+dk) = a-bi-cj-dk

        :return: conjugate quaternion ndarray
        """
        conj_num = self.view(np.ndarray)
        conj_num['x'] *= -1
        conj_num['y'] *= -1
        conj_num['z'] *= -1
        return conj_num.view(qn)

    @property
    def inv(self):
        """

        :return: inverse number of quaternion ndarray
        """
        # 1/qn
        qconj = self.conj
        q_innerproduct = self * qconj
        q_ip_inv = 1 / q_innerproduct['w']
        # The broadcast calculation is necessary here, but need to take care of the redundant dimension otherwise will run into dimensionality expansion problem all the time
        return np.squeeze(qconj * q_ip_inv[..., None]).view(qn)

    @property
    def qT(self):
        """
        Transposition of quaternion array returns the conjugated quaternions
        If want transposition without getting the conjugate number, use .T

        :return: transposed quaternion ndarray
        """

        return self.conj.T

    def azi(self):
        return np.angle(self['x'] + 1j * self['y'])

    def elv(self):
        return np.arctan(self['z'] / (self['xy'] ** 2).sum(axis=-1)[..., np.newaxis])

    @property
    def w(self):
        return self['w']

    @property
    def x(self):
        return self['x']

    @property
    def y(self):
        return self['y']

    @property
    def z(self):
        return self['z']

    @property
    def u(self):
        return self.azi()

    @property
    def v(self):
        # Return the double real number matrix (M x ... x 3) of the imaginary part
        return self.elv()

    @property
    def uv(self):
        return np.concatenate([self.azi(), self.elv()], axis=-1)

    @property
    def imag(self):
        """

        :return: quatenrion ndarray with real part set to 0;
        """
        imagpart = np.copy(self)
        imagpart['w'] = 0
        return imagpart.view(qn)

    @property
    def real(self):
        """

         :return: quatenrion ndarray with imag part set to 0;
         """

        realpart = np.copy(self)
        realpart['x'] = 0
        realpart['y'] = 0
        realpart['z'] = 0
        return realpart.view(qn)

    @property
    def imagpart(self):
        # Return the double real number matrix (M x ... x 3) of the imaginary part
        return self['xyz']

    @property
    def realpart(self):
        # Return the double real number matrix (M x ... x1) of the real part
        return self['w']

    @property
    def norm(self):
        # Return the norm (or the absolute value) of the quaternion number
        return np.sqrt(np.sum(self.matrixform ** 2, axis=-1))

    @property
    def angle(self):
        # Return the rotation angle
        return np.arccos(self.w / self.norm)*2

    @property
    def normalize(self):
        # Return the normalized quaternion number (norm = 1)
        return self / self.norm

    @property
    def leftmul_matrix(self):
        # Return the corresponding matrix for quaternion left multiplication
        # See http://www.euclideanspace.com/maths/algebra/realNormedAlgebra/quaternions/transforms/
        matself = self.view(np.ndarray)
        lm_mat = np.array([[matself['w'], matself['x'], matself['y'], matself['z']],
                           [matself['x'], -matself['w'], matself['z'], -matself['y']],
                           [matself['y'], -matself['z'], -matself['w'], matself['x']],
                           [matself['z'], matself['y'], -matself['x'], -matself['w']]])
        return lm_mat

    @property
    def conj_sandwich_mat(self):
        # Return the corresponding matrix QN so (qn1*qn2*qn.conj).matrixform = QN*[qn2.w;qn2.x,qn2.y;qn2.z]
        # Equal to rotation matrix
        return sliceDot(self.leftmul_matrix, self.leftmul_matrix)

    @property
    def sandwich_mat(self):
        # Return the corresponding matrix QN so (qn1*qn2*qn).matrixform = QN*[qn2.w;qn2.x,qn2.y;qn2.z]
        # Equal to reflection matrix
        return sliceDot(-self.leftmul_matrix, self.leftmul_matrix)

    def sum(self, **kwargs):
        # Not recommended, use the Q_num.sum function instead
        sum_axis = kwargs.pop('axis', None)
        if sum_axis:
            if sum_axis < 0:
                sum_axis -= 1
            elif sum_axis > self.ndim:
                raise np.AxisError('axis %d is out of bounds for array of dimension %d' % (sum_axis, self.ndim))
        else:
            sum_axis = 0
        kwargs['axis'] = sum_axis
        if not self.shape:
            q_mat_sum = self.matrixform
        else:
            q_mat_sum = np.sum(self.matrixform, **kwargs)
        return q_mat_sum.view(self.qn_dtype).view(qn)


################################### Functions ###################################
def sliceDot(mat1, mat2):
    """

    :param mat1: ndarray with ndim >= 2
    :param mat2: ndarray with ndim >= 2
    :return: inner product of each 2D slice of the two N-D matrices
    """
    ein_char = 'abcdefghijklmnopqrstuvwxyz'
    mat1string = ein_char[:mat1.ndim]
    mat2string = ein_char[1] + ein_char[mat1.ndim] + ein_char[2:mat1.ndim]
    outputstring = ein_char[0] + ein_char[mat1.ndim] + ein_char[2:mat1.ndim]
    ein_string = '%s,%s -> %s' % (mat1string, mat2string, outputstring)
    return np.einsum(ein_string, mat1, mat2)


def stack(*qn_array, **kwargs):
    # Same as np.stack
    stack_axis = kwargs.pop('axis', None)
    if stack_axis == 0:
        q_mat_stack = np.hstack([x.matrixform for x in qn_array], **kwargs)
    elif stack_axis == 1:
        q_mat_stack = np.vstack([x.matrixform for x in qn_array], **kwargs)
    else:
        q_mat_stack = np.stack([x.matrixform for x in qn_array], **kwargs)
    return q_mat_stack.view(qn.qn_dtype).view(qn)


def sum(*qn_array, **kwargs):
    # Same as np.sum
    sum_axis = kwargs.pop('axis', None)
    if sum_axis:
        if sum_axis < 0:
            sum_axis -= 1
        elif sum_axis > qn_array[0].ndim:
            raise np.AxisError('axis %d is out of bounds for array of dimension %d' % (sum_axis, qn_array[0].ndim))
    else:
        sum_axis = 0
    kwargs['axis'] = sum_axis

    q_mat_stack = np.squeeze(np.stack([x for x in qn_array], **kwargs))
    if not q_mat_stack.shape:
        q_mat_sum = q_mat_stack.view(qn).matrixform
    else:
        q_mat_sum = np.sum(q_mat_stack.view(qn).matrixform, **kwargs)
    return q_mat_sum.view(qn_array[0].qn_dtype).view(qn)


def nansum(*qn_array, **kwargs):
    # Same as np.nansum, calculate the sum but ignore nan numbers
    sum_axis = kwargs.pop('axis', None)
    if sum_axis:
        if sum_axis < 0:
            sum_axis -= 1
        elif sum_axis > qn_array[0].ndim:
            raise np.AxisError('axis %d is out of bounds for array of dimension %d' % (sum_axis, qn_array[0].ndim))
    else:
        sum_axis = 0
    kwargs['axis'] = sum_axis
    q_mat_stack = np.squeeze(np.stack([x for x in qn_array], **kwargs))
    if not q_mat_stack.shape:
        q_mat_sum = q_mat_stack.view(qn).matrixform
    else:
        q_mat_sum = np.nansum(q_mat_stack.view(qn).matrixform, **kwargs)
    return q_mat_sum.view(qn_array[0].qn_dtype).view(qn)


def mean(*qn_array, **kwargs):
    # Same as np.mean
    sum_axis = kwargs.pop('axis', None)
    if sum_axis:
        if sum_axis < 0:
            sum_axis -= 1
        elif sum_axis > qn_array[0].ndim:
            raise np.AxisError('axis %d is out of bounds for array of dimension %d' % (sum_axis, qn_array[0].ndim))
    else:
        sum_axis = 0
    kwargs['axis'] = sum_axis
    q_mat_stack = np.squeeze(np.stack([x for x in qn_array], **kwargs))
    if not q_mat_stack.shape:
        q_mat_sum = q_mat_stack.view(qn).matrixform
    else:
        q_mat_sum = np.mean(q_mat_stack.view(qn).matrixform, **kwargs)
    return q_mat_sum.view(qn_array[0].qn_dtype).view(qn)


def exp(qn1):
    # Exponetial calculation for quaternion numbers. Note the qn**2 is still not implemented
    coeff_real = np.exp(qn1['w'])
    coeff_imag_base = qn1.imag.norm
    coeff_imag = np.sin(coeff_imag_base) / coeff_imag_base
    temp_shape = qn1['w'].shape
    if not temp_shape:
        compact_product = np.zeros([qn1['w'].size], dtype=qn1.qn_dtype)
    else:
        compact_product = np.zeros([*temp_shape], dtype=qn1.qn_dtype)
    compact_product = np.full_like(compact_product, np.nan)
    compact_product['w'] = coeff_real * np.cos(coeff_imag_base)
    compact_product['x'] = qn1['x'] * coeff_imag
    compact_product['y'] = qn1['y'] * coeff_imag
    compact_product['z'] = qn1['z'] * coeff_imag
    return compact_product.view(qn)


def qdot(qn1, qn2):
    # Return the dot product of two quaternion number (as real number ndarray object)
    return -(qn1 * qn2).realpart


def qcross(qn1, qn2):
    # Return the cross product of two quaternion number (as quaternion ndarray object)
    return (qn1 * qn2).imag


def anglebtw(qn1, qn2):
    # Calculate the angle between 3d vectors represented with two quaternions whose real part = 0
    distbtw = (qn1.normalize - qn2.normalize).norm / 2
    errdist = np.abs(distbtw)
    if (errdist>1).any():
        warningmsg = "Setting the distance between the normalized points back to 1. Max. error:{err:.4f}".format(err=errdist.max()-1)
        warnings.warn(warningmsg)
        distbtw = np.minimum(np.maximum(distbtw, -1), 1)
    return np.arcsin(distbtw) * 2


def reflect(surf_normal, points):
    """
    Calculate the reflected 3d vectors representing with quaternions whose real part = 0

    :param surf_normal: normal vector for the reflection surface (quaternion)
    :param points: qn vectors or points to be reflected
    :return: reflected qn vectors/points
    """
    surf_normal /= surf_normal.norm
    return surf_normal * points * surf_normal


def reflect_matrix(surf_norm_vector):
    """

    :param surf_norm_vector: normal vector for the reflection surface (1 x 3 ndarray)
    :return: 4x4 ndarray matrix which perform reflection transformation
    """
    normtype = type(surf_norm_vector)
    if normtype == np.ndarray:
        surf_norm = qn(surf_norm_vector)
    elif normtype == qn:
        surf_norm = surf_norm_vector.imag.normalize  # The real part of the  orientation quaternion should always be 0
    else:
        raise Exception("Camera orientation should be a ndarray or a quaternion, instead its type is %s\n" % normtype)
    return surf_norm.sandwich_mat


def rotate(rot_axis, rot_point, rot_angle=None):
    """
    Perform 3D rotation
    Input:
        rot_axis: rotation axis (in quatennion ndarray form).
        rot_point: qn vectors or points to be rotated
        rot_angle (optional): if exist, it will update the qn number of the rot_axis
         with its value, if not applied, the rotation will be calculated only based on
         the rotation axis qn number
    Output:
        rotated qn vector/points
    """
    if rot_angle is not None:
        rot_axis = np.squeeze(exp(rot_angle / 2 * rot_axis.normalize))
    # rot_axis[np.isnan(rot_axis.norm)] *= 0
    return rot_axis * rot_point * rot_axis.conj


def rotation_matrix(rotation_axis, rot_angle=None):
    """

    :param rotation_axis:  rotation axis (1 x 3 ndarray)
    :param rot_angle: optional, real number defines the rotation angle
    :return:  4x4 ndarray matrix which perform rotation transformation
    """
    axistype = type(rotation_axis)
    if axistype == np.ndarray:
        rot_axis = qn(rotation_axis)
    elif axistype == qn:
        rot_axis = rotation_axis  # The real part of the  orientation quaternion should always be 0
    else:
        raise Exception('Camera orientation should be a ndarray or a quaternion, instead its type is %s\n' % axistype)
    if rot_angle is not None:
        rot_axis = np.squeeze(exp(rot_angle / 2 * rot_axis.normalize))
    return rot_axis.conj_sandwich_mat


def rotTo(fromQn, toQn):
    """
    Given the qn representing the current 3D orientation represented and the qn
    for the target 3D orientation, compute the rotation vectors to transform the
    current orienttaion to the target orientation
    Input:
        fromQn: current orientation qn vectors
        toQn:   target orientation qn vectors
    Output:
        the rotation quaternion for the rotation transform
    """
    toQn_normalized = toQn.normalize
    realpart = qdot(fromQn,toQn_normalized)
    imagpart = qcross(fromQn,toQn_normalized)
    realpart += (realpart+imagpart).norm
    trans_vec = imagpart+realpart
    return trans_vec.normalize


def projection(surf_normal_qn, proj_pnt_qn, on_plane=True):
    """
    Computing the projected quaternion
    ------------
    :param  surf_normal_qn: normal vector of the projection surface (quaternion)
    :param  proj_pnt_qn: qn vectors to be projected
    :param  on_plane: If true, project points onto the surface defined by the normal vector, otherwise projected on to the vector
    :return:  projected qn vectors
    """
    if on_plane:
        return (proj_pnt_qn + reflect(surf_normal_qn, proj_pnt_qn)) / 2
    else:
        return (proj_pnt_qn - reflect(surf_normal_qn, proj_pnt_qn)) / 2


def projection_matrix(projection_normal, flat_output=True):
    """
    Calculate the orthogonal projection transformation
    ------------
    :param projection_normal: 1 x 3 ndarray or a quaternion number; the camera's pointing direction
    :param flat_output: boolean, optional; if True (default), the output transformation quternion number or matrix will project the target point to the xy plane
    :return: transformation matrix or quaternion number for the corresponding orthogonal projection
    """
    normaltype = type(projection_normal)
    if normaltype == np.ndarray:
        projection_normal = qn(projection_normal)
    elif normaltype == qn:
        pass
    else:
        raise Exception('Camera orientation should be a ndarray or a quaternion, instead its type is %s\n' % normaltype)

    if all(projection_normal.imagpart.flatten() == 0):
        raise Exception('Input projection normal vector is a zero vector')
    else:
        reflect_mat = reflect_matrix(projection_normal)
        projection_mat = (np.eye(4) + np.squeeze(reflect_mat)) / 2

        if flat_output:
            xynorm = qn(np.array([0, 0, 1]))  # The normal quaternion number for x-y plane
            if all(projection_normal.imagpart.flatten()[:2] == 0):
                backrot = rotTo(projection_normal, xynorm)
            else:
                projection_xy = np.copy(projection_normal).view(
                    qn)  # Intermediate quaternnion for rotate the projected result to the x-y plane
                projection_xy['z'] *= 0
                backrot = rotTo(projection_xy, xynorm) * rotTo(projection_normal, projection_xy)
            backrot_mat = rotation_matrix(backrot)
            return np.dot(np.squeeze(backrot_mat), projection_mat)
        else:
            return projection_mat

def lerp(pnt1:qn,pnt2:qn,num_pnt=10):
    grad = np.linspace(0,1,num_pnt)[:,np.newaxis]
    return pnt1*(1-grad)+pnt2*grad


def slerp(pnt1:qn,pnt2:qn,center:qn = qn([0,0,0]),num_pnt=10):
    pnt1v = pnt1 - center
    pnt2v = pnt2 - center
    pnt1v_norm = pnt1v.norm
    pnt2v_norm = pnt2v.norm
    pnt1v = pnt1v.normalize
    pnt2v = pnt2v.normalize
    rotation_vec = rotTo(pnt1v, pnt2v)
    arc_pnt = rotate(rotation_vec.imag.normalize, pnt1v, np.linspace(0, rotation_vec.angle, num_pnt))
    arc_pnt += center
    return arc_pnt


# def orthogonal_projection(camera_orientation, flat_output=True, outputformat='qn'):
#     oritype = type(camera_orientation)
#     if oritype == np.ndarray:
#         camori = qn(camera_orientation)
#     elif oritype == qn:
#         camori = camera_orientation.imag  # The real part of the  orientation quaternion should always be 0
#     else:
#         raise Exception('Camera orientation should be a ndarray or a quaternion, instead its type is %s\n' % oritype)