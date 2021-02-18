from collections.abc import Callable
class chainProcessor:
    """"""
    def __init__(self,his_queue_size = 1):
        self._func = {}
        self.__arginfo = {}
        self._arg = {}
        self._kwarg = {}
        self._maxHistRec = his_queue_size
        self._his_queue = [None] * self._maxHistRec
        self._output = [None] * self._maxHistRec

    def reg(self,name:str,func:Callable):
        self._func[name] = func

        if func.__kwdefaults__:
            self._kwarg[name] = func.__kwdefaults__
        else:
            self._kwarg[name] = {}

        if func.__defaults__:
            default_arg_lens = func.__code__.co_argcount - len(func.__defaults__)
            opt_arg_len = len(func.__defaults__)
            t = zip(func.__code__.co_varnames[default_arg_lens:default_arg_lens + opt_arg_len], func.__defaults__)
            self._kwarg[name].update(dict(t))
        else:
            default_arg_lens = func.__code__.co_argcount

        self._arg[name] = tuple([None] * default_arg_lens)

        self.__arginfo[name] = (default_arg_lens,self._kwarg[name])


    def exc(self,func_name,*args,**kwargs):
        if len(self._arg[func_name]) == len(args):
            self._arg[func_name] = args
        if set(kwargs.keys()) == set(self._kwarg[func_name].keys())&set(kwargs.keys()):
            self._kwarg[func_name].update(kwargs)
        self._output.append(self._func[func_name](*self._arg[func_name],**self._kwarg[func_name]))
        self._output.pop(0)
        self._his_queue.append(func_name)
        self._his_queue.pop(0)
        return self

    @property
    def fetch(self,func_idx = -1):
        return self._his_queue[func_idx],self._output[func_idx]


    def fetch_(self,func_idx = -1):
        if isinstance(func_idx,int):
            return self._his_queue[func_idx],self._output[func_idx]
        elif isinstance(func_idx,list):
            return self._his_queue[func_idx[0]:func_idx[1]],self._output[func_idx[0]:func_idx[1]]
        elif func_idx == "all":
            return self._his_queue,self._output

    def get_arg(self,func_name):
        return self._arg[func_name],self._kwarg[func_name]

    def pop(self,func_idx=0):
        self._output.pop(func_idx)
        self._output.insert(0,None)
        self._his_queue.pop(func_idx)
        self._his_queue.insert(0, None)
        return self

    def clear(self):
        self._his_queue = [None] * self._maxHistRec
        self._output = [None] * self._maxHistRec
