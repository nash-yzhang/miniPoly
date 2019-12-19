import numpy
from multiprocessing import Process,Queue
from glumpy import app, gl, glm
import time
def p1(q):

    q.put(time.time())

q = Queue()
p = Process(target = p1, args = (q,))
print(q.get())