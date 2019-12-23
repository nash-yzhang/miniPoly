import multiprocessing as mp
from queue import Queue
from functools import update_wrapper,wraps
from IPython import embed

class _bugger(object):
    def __init__(self, func, varname):
        self.varname = varname
        self.func    = func
        self.varbuffer = []
        self.__module__ = "__main__"

    def __call__(self,*args,**kwargs):
        return self.func(self,*args,**kwargs)

    def append(self,localvar):
        self.varbuffer.insert(0,{key: value for key,value in localvar.items() if key in self.varname})

def Bugger(varname,function = None):
    if function:
        return _bugger(function,varname)
    else:
        @wraps(function)
        def wrapper(function,**kwargs):
            return _bugger(function,varname,**kwargs)
        return wrapper