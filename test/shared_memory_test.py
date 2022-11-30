# from bin import minion
# import numpy as np
#
# a = {'bb_a': np.ones((63,50)).tolist(), 'ccd': 0, 'e':None, 'eo': (1,False,True,['bb_a','ccd',' ',]), ' k ': '    '}
# sb_a = minion.SharedBuffer('a',data=a,size=2**14)
# #%%
# from time import time
# cc = time()
# for i in range(1000):
#     sb_a.read()
#     sb_a.write(a)
# print(time()-cc)
# #%%
# sb_b = minion.SharedBuffer('a',create=False)
# sb_b.valid_size
# #%%
# new_a = {'ccd': sb_a.read()['bb_a'], 'ek': 0, 'eo': None}
# sb_b.write(new_a)
# #%%
# c = sb_b.read()
# #%%
# sb_a.close()
# sb_b.close()
#%%
from bin.minion import SharedBuffer, SharedDict

class A(object):
    def __init__(self,sbf):
        self._b = SharedDict(sbf, {"message": "",
                          "last_message": ""})

    @property
    def b(self):
        return self._b

sb_a = SharedBuffer('a',size=2**14)
a = A('a')
a.b['message'] = 'hello'
a.b['last_message'] = 'world'

print(a.b['message'])
# ''
print(a.b['last_message'])
#%%
# a.b['asldf'] = '1231'
a.b.update({'asdfasdfas': 1})
#%%
a.b.update({'asl': 'k', 'message': 123123123})
#%%
a.b.close()

