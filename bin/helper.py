from collections.abc import Callable
import imgui
from copy import deepcopy

class chainProcessor:
    """"""

    def __init__(self, his_queue_size=1):
        self._func = {}
        # self.__arginfo = {}
        # self._arg = {}
        self._kwarg = {}
        self._appendix = {}
        self._maxHistRec = his_queue_size
        self._his_queue = [None] * self._maxHistRec
        self._output = [None] * self._maxHistRec

    def reg(self, name: str, func: Callable, appendix={}):
        self._func[name] = func
        self._appendix[name] = appendix
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

        # self._arg[name] = tuple([None] * default_arg_lens)
        # self.__arginfo[name] = (default_arg_lens, self._kwarg[name])

    def exc(self, func_name, *args, **kwargs):
        # if len(self._arg[func_name]) == len(args):
        #     self._arg[func_name] = args
        if set(kwargs.keys()) == set(self._kwarg[func_name].keys()) & set(kwargs.keys()):
            self._kwarg[func_name].update(kwargs)
        self._output.append(self._func[func_name](*args, **self._kwarg[func_name]))
        self._output.pop(0)
        self._his_queue.append(func_name)
        self._his_queue.pop(0)
        return self

    # def fetch(self, func_idx=-1):
    #     return self._his_queue[func_idx], deepcopy(self._output[func_idx])

    def fetch_(self, func_idx=-1):
        if isinstance(func_idx, int):
            return self._his_queue[func_idx], self._output[func_idx]
        elif isinstance(func_idx, list):
            return self._his_queue[func_idx[0]:func_idx[1]], self._output[func_idx[0]:func_idx[1]]
        elif func_idx == "all":
            return self._his_queue, self._output

    # def get_arg(self, func_name):
    #     return self._arg[func_name], self._kwarg[func_name]

    def pop(self, func_idx=0):
        self._output.pop(func_idx)
        self._output.insert(0, None)
        self._his_queue.pop(func_idx)
        self._his_queue.insert(0, None)
        return self

    def clear(self):
        self._his_queue = [None] * self._maxHistRec
        self._output = [None] * self._maxHistRec

def add_imguiWidget(widget_args: list, key, val):
    data_type = widget_args[0]
    other_args = widget_args[1:]
    if data_type == "bool":
        _, recur_val = imgui.checkbox(key, val)

    elif data_type == "int":
        clicked, recur_val = imgui.slider_int(key, val, *other_args)
        imgui.same_line()
        clicked2, recur_val2 = imgui.input_int(key + ' ', val)
        if not clicked and clicked2:
            recur_val = recur_val2

    elif data_type == "int2":
        clicked, recur_val = imgui.slider_int2(key, *val, *other_args)
        imgui.same_line()
        clicked2, recur_val2 = imgui.input_int2(key + ' ', val)
        if not clicked and clicked2:
            recur_val = recur_val2

    elif data_type == "int3":
        clicked, recur_val = imgui.slider_int3(key, *val, *other_args)
        imgui.same_line()
        clicked2, recur_val2 = imgui.input_int3(key + ' ', val)
        if not clicked and clicked2:
            recur_val = recur_val2

    elif data_type == "int4":
        clicked, recur_val = imgui.slider_int4(key, *val, *other_args)
        imgui.same_line()
        clicked2, recur_val2 = imgui.input_int4(key + ' ', val)
        if not clicked and clicked2:
            recur_val = recur_val2

    elif data_type == "float":
        clicked, recur_val = imgui.slider_float(key, val, *other_args)
        imgui.same_line()
        clicked2, recur_val2 = imgui.input_float(key + ' ', val)
        if not clicked and clicked2:
            recur_val = recur_val2

    elif data_type == "float2":
        clicked, recur_val = imgui.slider_float2(key, *val, *other_args)
        imgui.same_line()
        clicked2, recur_val2 = imgui.input_float2(key + ' ', val)
        if not clicked and clicked2:
            recur_val = recur_val2

    elif data_type == "float3":
        clicked, recur_val = imgui.slider_float3(key, *val, *other_args)
        imgui.same_line()
        clicked2, recur_val2 = imgui.input_float3(key + ' ', val)
        if not clicked and clicked2:
            recur_val = recur_val2

    elif data_type == "float4":
        clicked, recur_val = imgui.slider_float4(key, *val, *other_args)
        imgui.same_line()
        clicked2, recur_val2 = imgui.input_float4(key + ' ', val)
        if not clicked and clicked2:
            recur_val = recur_val2

    elif data_type == "str":
        clicked, recur_val = imgui.input_text(key, val, *other_args)

    return recur_val


def switch_gui(cpobj: chainProcessor, gui_idx, selected_idx):
    func_called, output_fetched = cpobj.fetch_('all')
    img_process = [i for i in func_called if i]
    _, gui_idx = imgui.listbox("", gui_idx, img_process)
    imgui.same_line()
    clicked = imgui.button("Update visualization")
    if clicked:
        selected_idx = gui_idx
    selected_func_name = img_process[gui_idx]
    if selected_func_name:
        kwarg_selected = cpobj._kwarg[selected_func_name]
        for key, val in kwarg_selected.items():
            if key in cpobj._appendix[selected_func_name]:
                iter_args = cpobj._appendix[selected_func_name][key]
                cpobj._kwarg[selected_func_name][key] = \
                    add_imguiWidget(iter_args, key, val)
    return deepcopy(output_fetched[selected_idx + len(cpobj._output) - len(img_process)]), gui_idx, selected_idx
