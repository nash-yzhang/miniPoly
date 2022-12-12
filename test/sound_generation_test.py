from pysinewave import SineWave
import time
import numpy as np

sound_array= [[13,.5],[13,.5],[13,.5],
              [9,.3],[16,.05],[13,.5],
              [9,.3],[16,.15],[13,.5]]

def play_sound(arr):
    cumuT = 0
    sinewave = SineWave(pitch=arr[0][1],pitch_per_second=2000,decibels_per_second=2000)
    sinewave.play()
    for i in arr:
        f,t = i
        sinewave.set_volume(-1000)
        time.sleep(0.04)
        sinewave.set_pitch(f)
        sinewave.set_volume(0)
        time.sleep(t)
        cumuT+=t
    sinewave.stop()
    return cumuT

a = time.time()
T = play_sound(sound_array)
print(T - (time.time()-a))
#%%
