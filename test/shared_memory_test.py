from bin import minion
import numpy as np

a = {'bb_a': np.ones((109,100,3)).tolist(), 'ccd': 0, 'e':None, 'eo': (1,False,True,['bb_a','ccd',' ',]), ' k ': '    '}
sb_a = minion.SharedBuffer('a',data=a,size=2**32)
#%%
sb_b = minion.SharedBuffer('a',create=False)
sb_b.valid_size
#%%
new_a = {'ccd': sb_a.read()['bb_a'], 'ek': 0, 'eo': None}
sb_b.write(new_a)
#%%
c = sb_b.read()
#%%
sb_a.close()
sb_b.close()


