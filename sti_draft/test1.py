#%%
import time

from serial import Serial
import numpy as np
from time import sleep
serial = Serial("com7", 38400)
#%
n_device = 6
def presstobyte(mat):
    return list(np.sum(mat*2**np.arange(mat.shape[0]),axis=1))
orimat = np.zeros([8,8*n_device]).astype(int)
orimat[:,np.arange(0,orimat.shape[1],4)] = 1
orimat[:,np.arange(1,orimat.shape[1],4)] = 1
for i in range(300):
    orimat = np.roll(orimat,1,axis=1)
    msg = []
    for o in range(n_device):
        msg += presstobyte(orimat[:,o*8:(o+1)*8].T)
    serial.write(bytes(msg))
    sleep(1/10)
serial.close()
#%%
# # #%%
# # from pymata_aio.pymata3 import PyMata3
# # from pymata_aio.constants import Constants
# # from LEDmatrix import MaxMatrix, make_sprite
# #
# #
# # board = PyMata3(arduino_wait=5)
# # DIN, CLK, CS = 11, 13, 12
# # mm = MaxMatrix(board, DIN, CS, CLK)
# # #%%
# # import numpy as np
# # orimat = np.zeros([8,8])
# # orimat[:,np.arange(0,7,2)] = 1
# # for i in range(100):
# #     orimat = np.roll(orimat,1,axis=1)
# #     mm.write_sprite(make_sprite(orimat))
# # #%%
# # mm.set_row(0, 0b1011011)
# # #%%
