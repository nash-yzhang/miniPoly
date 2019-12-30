import multiprocessing as mp
from functools import wraps
# from IPython import embed
# noinspection SpellCheckingInspection

class _bugger (object) :
    _func = None

    def __init__(self, func, varname):
        self.varname = varname
        self._func = func
        self.varbuffer = mp.Queue()
        self.Process = mp.Process (target=self._func, args=(self,))

    def append(self, localvar, varname=None) :
        if not varname :
            varname = self.varname
        tout = {}
        for key, value in localvar.items () :
            if key in varname :
                tout[key] = value
        self.varbuffer.put (tout)

    def add_method(self, cls):
        def decorator(newMethod):
            @wraps(newMethod)
            def wrapper(self,*args,**kwargs):
                return newMethod(*args,**kwargs)
            setattr(cls,newMethod.__name__,wrapper)
            return newMethod
        return decorator


def Bugger(varname, func=None) :
    if func :
        return _bugger (func, varname)
    else :
        @wraps (func)
        def wrapper(func, **kwargs) :
            return _bugger (func, varname)

        return wrapper
