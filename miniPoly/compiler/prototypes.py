import csv
import os
import time

import cv2

from miniPoly.core.minion import TimerMinionMixin, TimerMinion

import traceback

class AbstractCompiler(TimerMinionMixin):
    _processHandler: TimerMinion

    def __init__(self, processHandler: TimerMinion):
        super().__init__()
        self._processHandler = processHandler
        self._processHandler.add_callback('default', self._on_time)
        self.refresh_interval = self._processHandler.refresh_interval
        self.name = self._processHandler.name

    def _on_time(self, t):
        if self.status() <= 0:
            self._on_close()
        try:
            self.on_time(t)
        except:
            self.error('Error in on_time')
            self.error(traceback.format_exc())
        self._processHandler.on_time(t)

    def on_time(self, t):
        pass

    def on_protocol(self, t):
        pass

    def _on_close(self):
        self.set_state('status', -1)
        self.on_close()

    def on_close(self):
        pass


class StreamingCompiler(AbstractCompiler):

    def __init__(self, *args, timer_minion=None, trigger_minion=None, **kwargs):
        '''
        A compiler for the IOHandler class that receives and save all data from its connected minions.
        :param timer_minion: name of the minion that generates timestamps
        :param trigger_minion: the name of a foreign minion whose state "StreamToDisk" will trigger the streaming
        '''
        super().__init__(*args, **kwargs)

        self._timer_minion = timer_minion
        self._trigger_minion = trigger_minion
        self.trigger = None

        # Initializing saving handler
        self._state_stream_fn = None
        self._state_stream_handler = None
        self._state_stream_writer = None
        self._buffer_handle_param = {}
        self._buffer_streaming_handle = {}
        self._streaming_start_time = 0
        self.streaming = False

        self._streaming_states = {}
        self._streaming_buffers = {}
        self._shared_states = []
        self._shared_buffers = []

        # Initializing saving parameters and create the corresponding shared state to receive GUI control
        self.saving_param = {'StreamToDisk': False,
                             'SaveDir': None,
                             'SaveName': None}

        # for k, v in self.saving_param.items():
        #     self.create_state(k, v)

    def create_streaming_state(self, state_name, val, shared=False, use_buffer=False, dtype=None):
        if state_name in self._streaming_states:
            self.error('{} is already in the streaming state list'.format(state_name))
        else:
            self._streaming_states[state_name] = val
            if shared:
                self.create_state(state_name, val, use_buffer=use_buffer, dtype=dtype)
                self._shared_states.append(state_name)
                self.info('Created shared streaming state [{}]'.format(state_name))
            else:
                self.info('Created local streaming state [{}]'.format(state_name))

    def remove_streaming_state(self, mi_name, state_name):
        if state_name in self._streaming_states:
            del self._streaming_states[state_name]
            if state_name in self._shared_states:
                self._shared_states.remove(state_name)
                self.remove_state(state_name)
            self.info('Removed {} from the streaming state list of {}'.format(state_name, mi_name))
        else:
            self.error('{} is not registered for streaming'.format(mi_name))

    def create_streaming_buffer(self, buffer_name, buffer_val, saving_opt=None, shared=False):
        if buffer_name in self._streaming_buffers:
            self.error('{} is already in the streaming buffer list'.format(buffer_name))
        else:
            self._streaming_buffers[buffer_name] = [buffer_val, saving_opt]
            if shared:
                self._shared_buffers.append(buffer_name)
                self.create_shared_buffer(buffer_name, buffer_val)
                self.info('Created shared streaming buffer [{}]'.format(buffer_name))
            else:
                self.info('Created local streaming buffer [{}]'.format(buffer_name))

    def remove_streaming_buffer(self, buffer_name):
        if buffer_name in self._streaming_buffers.keys():
            del self._streaming_buffers[buffer_name]
            if buffer_name in self._shared_buffers:
                self.remove_shared_buffer(buffer_name)
                self._shared_buffers.remove(buffer_name)
            self.info('Removed {} from the streaming buffer list'.format(buffer_name))
        else:
            self.error('Cannot remove {} as it is not registered for streaming'.format(buffer_name))

    def get_streaming_state(self, state_name):
        if state_name in self._streaming_states.keys():
            if state_name in self._shared_states:
                self._streaming_states[state_name] = self.get_state(state_name)
            return self._streaming_states[state_name]
        else:
            self.error('{} is not registered for streaming'.format(state_name))
            return None

    def set_streaming_state(self, state_name, val):
        if state_name in self._streaming_states.keys():
            if state_name in self._shared_states:
                self.set_state(state_name, val)
            else:
                self._streaming_states[state_name] = val
        else:
            self.error('{} is not registered for streaming'.format(state_name))

    def get_streaming_buffer(self, buffer_name):
        if buffer_name in self._streaming_buffers.keys():
            if buffer_name in self._shared_buffers:
                self._streaming_buffers[buffer_name][0] = self.get_state(buffer_name)
            return self._streaming_buffers[buffer_name]
        else:
            self.error('{} is not registered for streaming'.format(buffer_name))
            return None

    def set_streaming_buffer(self, buffer_name, val):
        if buffer_name in self._streaming_buffers.keys():
            if buffer_name in self._shared_buffers:
                self.set_state(buffer_name, val)
            else:
                self._streaming_buffers[buffer_name][0] = val
        else:
            self.error('{} is not registered for streaming'.format(buffer_name))

    def _streaming_setup(self):
        is_streaming = self.get_state_from(self._trigger_minion, 'StreamToDisk')
        if self.should_stream():  # check if the compiler should be involved in streaming
            if self.watch_state('StreamToDisk', is_streaming):  # Triggered at the onset and the end of streaming
                if is_streaming:
                    err = self._prepare_streaming()
                    if not err:
                        self._start_streaming()
                else:  # close all files before streaming stops
                    self._stop_streaming()

    def should_stream(self):
        return True

    def _prepare_streaming(self):
        err = False
        stateStreamHandlerFn = None
        bufferHandlerParam = {}

        save_dir = self.get_state_from(self._trigger_minion, 'SaveDir')
        file_name = self.get_state_from(self._trigger_minion, 'SaveName') + "_" + self.name
        missing_saving_param = [i for i in [save_dir, file_name] if i is None]
        if len(missing_saving_param) > 0:
            err = True
            self.error("Streaming could not start because of the following undefined parameter(s): {}".format(
                missing_saving_param))

        # Check if the save directory exists and any file with the same name already exists
        if not err:
            if os.path.isdir(save_dir):
                stateStreamHandlerFn = os.path.join(save_dir, f"{file_name}.csv")
                if os.path.isfile(stateStreamHandlerFn):
                    err = True
                    self.error("Streaming could not start because the state csv file {} already exists".format(
                        stateStreamHandlerFn))

                errFnList = []
                for buf_name, v in self._streaming_buffers.items():
                    bufferHandlerParam[buf_name] = {}
                    if v[1] is None or v[1] == 'binary':
                        BIN_Fn = os.path.join(save_dir, f"{file_name}_{self.name}_{buf_name}.bin")
                        if os.path.isfile(BIN_Fn):
                            errFnList.append(f"{file_name}_{self.name}_{buf_name}.bin")
                            err = True
                        else:
                            bufferHandlerParam[buf_name]['type'] = 'binary'
                            bufferHandlerParam[buf_name]['fn'] = BIN_Fn
                    elif v[1] == 'movie':
                        BIN_Fn = os.path.join(save_dir, f"{file_name}_{self.name}_{buf_name}.avi")
                        if os.path.isfile(BIN_Fn):
                            errFnList.append(f"{file_name}_{self.name}_{buf_name}.avi")
                            err = True
                        else:
                            bufferHandlerParam[buf_name]['type'] = 'movie'
                            bufferHandlerParam[buf_name]['fn'] = BIN_Fn
                    else:
                        bufferHandlerParam[buf_name]['type'] = 'disabled'
                        bufferHandlerParam[buf_name]['fn'] = None
                        self.warning("Unknown streaming format: [{}];  Streaming of {} from {} is disabled".format(v[1],
                                                                                                                   buf_name,
                                                                                                                   self.name))
                    bufferHandlerParam[buf_name]['shape'] = v[0].shape[:-1]

                if len(errFnList) > 0:
                    self.error("Streaming could not start because the following buffer files already exist: {}".format(
                        errFnList))
                    err = True
            else:
                err = True
                self.error("Streaming could not start because the save directory {} does not exist".format(save_dir))

        if not err:
            self._state_stream_fn = stateStreamHandlerFn
            self._bufferHandlerParam = bufferHandlerParam

        return err

    def _start_streaming(self):
        # reset buffered state
        for state_name in self._streaming_states:
            self.watch_state(state_name, None)
        # Create the state csv file
        self._state_stream_handler = open(self._state_stream_fn, 'w', newline='')
        self._state_stream_writer = csv.writer(self._state_stream_handler)
        name_row = ['Time']
        for state_name in self._streaming_states:
            name_row.append(f"{self.name}_{state_name}")
        self._state_stream_writer.writerow(name_row)

        # Create the buffer files
        for buf_name, v in self._streaming_buffers.items():
            fn = self._bufferHandlerParam[buf_name]['fn']
            fshape = self._bufferHandlerParam[buf_name]['shape']
            if v[1] is None or v[1] == 'binary':
                self._buffer_streaming_handle[buf_name] = (open(fn, 'wb'), v[1])
            elif v[1] == 'movie':
                self._buffer_streaming_handle[buf_name] = (cv2.VideoWriter(fn, cv2.VideoWriter_fourcc(*'MJPG'),
                                                                           int(1000 / self.refresh_interval),
                                                                           (fshape[1], fshape[0])), 'movie')
            else:
                self._buffer_streaming_handle[buf_name] = (None, None)

        self._streaming_start_time = self.get_timestamp()
        self.streaming = True

    def _stop_streaming(self):
        if self.streaming:
            self.streaming = False
            self._state_stream_handler.close()

            for buf_name, v in self._buffer_streaming_handle.items():
                if v[1] is None or v[1] == 'binary':
                    v[0].close()
                elif v[1] == 'movie':
                    v[0].release()
                else:
                    pass

            self._state_stream_fn = None
            self._state_stream_handler = None
            self._state_stream_writer = None
            self._buffer_handle_param = {}
            self._buffer_streaming_handle = {}
            self._streaming_start_time = 0
            self.streaming = False

    def _streaming(self):
        if self.streaming:
            t = self.get_timestamp() - self._streaming_start_time
            val_row = [t]
            state_changed = False
            for state_name in self._streaming_states:
                state_val = self.get_streaming_state(state_name)
                if self.watch_state(state_name, state_val):
                    state_changed = True
                val_row.append(state_val)

            if state_changed:
                self._state_stream_writer.writerow(val_row)
                for buf_name, v in self._streaming_buffers.items():
                    if v[1] is None or v[1] == 'binary':
                        self._buffer_streaming_handle[buf_name][0].write(bytearray(v[0]))
                    elif v[1] == 'movie':
                        self._buffer_streaming_handle[buf_name][0].write(v[0].repeat(3,axis=2))
                    else:
                        pass

    def get_timestamp(self):
        if self._timer_minion is not None:
            if self._timer_minion != self.name:
                return self.get_state_from(self._timer_minion, 'timestamp') / 1000
            else:
                return self.get_state('timestamp') / 1000
        else:
            return time.perf_counter()

    def on_time(self, t):
        self._streaming_setup()
        self._streaming()


class IOStreamingCompiler(AbstractCompiler):

    def __init__(self, *args, ts_minion_name=None, state_dict={}, buffer_dict={}, buffer_saving_opt={}, trigger=None,
                 **kwargs):
        '''
        A compiler for the IOHandler class that receives and save all data from its connected minions.
        :param state_dict: a dictionary whose keys will be the names of the minions and the values will be lists of
                            parameters to save in a csv file.
        :param buffer_dict: a dictionary whose keys will be the names of the minions and the values will be lists of
                            buffers to save.
        :param buffer_saving_opt: a dictionary whose keys will be the names of the minions and the values will be option
                            dictionaries. The key of the option dictionary is the name of the buffer and the value is
                            the saving options.
        :param trigger: the name of a foreign state whose change will trigger the saving of all data.
        '''
        super().__init__(*args, **kwargs)

        self._ts_minion_name = ts_minion_name
        self.state_dict = state_dict
        self.buffer_dict = buffer_dict
        self.buffer_saving_opt = buffer_saving_opt
        self._trigger_state_name = trigger
        self.trigger = None

        # Initializing saving handler
        self._state_stream_fn = None
        self._state_stream_handler = None
        self._state_stream_writer = None
        self._buffer_handle_param = {}
        self._buffer_streaming_handle = {}
        self._streaming_start_time = 0
        self.streaming = False

        for mi_name, buf_name in self.buffer_dict.items():
            self._buffer_streaming_handle[mi_name] = {}
            for i_buf in buf_name:
                if self.buffer_saving_opt.get(mi_name) is not None:
                    opt = self.buffer_saving_opt[mi_name].get('i_buf')
                else:
                    opt = None
                self._buffer_streaming_handle[mi_name][i_buf] = (None, opt)

        # Initializing saving parameters and create the corresponding shared state to receive GUI control
        self.saving_param = {'StreamToDisk': False,
                             'SaveDir': None,
                             'SaveName': None,
                             'InitTime': None}

        for k, v in self.saving_param.items():
            self.create_state(k, v)

    def add_streaming_state(self, mi_name, state_name):
        if self.state_dict.get(mi_name) is None:
            self.state_dict[mi_name] = [state_name]
            self.info('Created streaming state list for {} and added {} to the list'.format(mi_name, state_name))
        else:
            if state_name not in self.state_dict[mi_name]:
                self.state_dict[mi_name].append(state_name)
                self.info('Added {} to the streaming state list of {}'.format(state_name, mi_name))
            else:
                self.error('{} is already in the streaming state list of {}'.format(state_name, mi_name))

    def remove_streaming_state(self, mi_name, state_name):
        if self.state_dict.get(mi_name) is not None:
            if state_name in self.state_dict[mi_name]:
                self.state_dict[mi_name].remove(state_name)
                self.info('Removed {} from the streaming state list of {}'.format(state_name, mi_name))
            else:
                self.error('{} is not in the streaming state list of {}'.format(state_name, mi_name))
        else:
            self.error('{} is not registered for streaming'.format(mi_name))

    def add_streaming_buffer(self, mi_name, buffer_name, saving_opt=None):
        if self.buffer_dict.get(mi_name) is None:
            self.buffer_dict[mi_name] = [buffer_name]
            self._buffer_streaming_handle[mi_name][buffer_name] = (None, saving_opt)
            self.info('Created streaming buffer list for {} and added {} to the list'.format(mi_name, buffer_name))
        else:
            if buffer_name not in self.buffer_dict[mi_name]:
                self.buffer_dict[mi_name].append(buffer_name)
                self._buffer_streaming_handle[mi_name][buffer_name] = (None, saving_opt)
                self.info('Added {} to the streaming buffer list of {}'.format(buffer_name, mi_name))
            else:
                self.info('{} is already in the streaming buffer list of {}'.format(buffer_name, mi_name))

    def remove_streaming_buffer(self, mi_name, buffer_name):
        if self.buffer_dict.get(mi_name) is not None:
            if buffer_name in self.buffer_dict[mi_name]:
                self.buffer_dict[mi_name].remove(buffer_name)
                self._buffer_streaming_handle[mi_name].pop(buffer_name)
                self.info('Removed {} from the streaming buffer list of {}'.format(buffer_name, mi_name))
            else:
                self.error('{} is not in the streaming buffer list of {}'.format(buffer_name, mi_name))
        else:
            self.error('{} is not registered for streaming'.format(mi_name))

    def _streaming_setup(self):
        if_streaming = self.get_state('StreamToDisk')
        if self.watch_state('StreamToDisk', if_streaming):  # Triggered at the onset and the end of streaming
            if if_streaming:
                err = self._prepare_streaming()
                if not err:
                    self._start_streaming()
            else:  # close all files before streaming stops
                self._stop_streaming()

    def _prepare_streaming(self):
        err = False
        missing_state_list = []
        missing_buffer_list = []
        stateStreamHandlerFn = None
        bufferHandlerParam = {}

        # Check if all the shared states and buffers are available
        for mi_name, state_name in self.state_dict.items():
            i_state_dict = self.get_state_from(mi_name, 'ALL')
            for i_state in state_name:
                if i_state_dict.get(i_state) is None:
                    missing_state_list.append((mi_name, i_state))

        for mi_name, buffer_name in self.buffer_dict.items():
            bufferHandlerParam[mi_name] = {}
            for i_buf in buffer_name:
                buf_val = self.get_state_from(mi_name, i_buf)
                if buf_val is None:
                    missing_buffer_list.append((mi_name, i_buf))
                else:
                    bufferHandlerParam[mi_name][i_buf] = {}
                    bufferHandlerParam[mi_name][i_buf]['shape'] = buf_val.shape

        if len(missing_state_list) > 0:
            err = True
            self.error("Streaming could not start because the shared state(s) cannot be found:\n {}".format(
                missing_state_list))
        if len(missing_buffer_list) > 0:
            err = True
            self.error("Streaming could not start because the shared buffer(s) cannot be found:\n {}".format(
                missing_buffer_list))

        # Check if all the saving parameters are defined
        if not err:
            save_dir = self.get_state('SaveDir')
            file_name = self.get_state('SaveName')
            # start_time = self.get_state('InitTime')
            # missing_saving_param = [i for i in [save_dir, file_name, start_time] if i is None]
            missing_saving_param = [i for i in [save_dir, file_name] if i is None]
            if len(missing_saving_param) > 0:
                err = True
                self.error("Streaming could not start because of the following undefined parameter(s): {}".format(
                    missing_saving_param))

        # Check if the save directory exists and any file with the same name already exists
        if not err:
            if os.path.isdir(save_dir):
                stateStreamHandlerFn = os.path.join(save_dir, f"{file_name}.csv")
                if os.path.isfile(stateStreamHandlerFn):
                    err = True
                    self.error("Streaming could not start because the state csv file {} already exists".format(
                        stateStreamHandlerFn))

                errFnList = []
                for mi, i_buf in self._buffer_streaming_handle.items():
                    for buf_name, v in i_buf.items():
                        if v[1] is None or v[1] == 'binary':
                            BIN_Fn = os.path.join(save_dir, f"{file_name}_{mi}_{buf_name}.bin")
                            if os.path.isfile(BIN_Fn):
                                errFnList.append(f"{file_name}_{mi}_{buf_name}.bin")
                                err = True
                            else:
                                bufferHandlerParam[mi][buf_name]['type'] = 'binary'
                                bufferHandlerParam[mi][buf_name]['fn'] = BIN_Fn
                        elif v[1] == 'movie':
                            BIN_Fn = os.path.join(save_dir, f"{file_name}_{mi}_{buf_name}.avi")
                            if os.path.isfile(BIN_Fn):
                                errFnList.append(f"{file_name}_{mi}_{buf_name}.avi")
                                err = True
                            else:
                                bufferHandlerParam[mi][buf_name]['type'] = 'movie'
                                bufferHandlerParam[mi][buf_name]['fn'] = BIN_Fn
                        else:
                            bufferHandlerParam[mi][buf_name]['type'] = 'disabled'
                            bufferHandlerParam[mi][buf_name]['fn'] = None
                            self.warning("Streaming of {} from {} is disabled".format(buf_name, mi))

                if len(errFnList) > 0:
                    self.error("Streaming could not start because the following buffer files already exist: {}".format(
                        errFnList))
                    err = True
            else:
                err = True
                self.error("Streaming could not start because the save directory {} does not exist".format(save_dir))

        if not err:
            self._state_stream_fn = stateStreamHandlerFn
            self._bufferHandlerParam = bufferHandlerParam

        return err

    def _start_streaming(self):
        # Create the state csv file
        self._state_stream_handler = open(self._state_stream_fn, 'w', newline='')
        self._state_stream_writer = csv.writer(self._state_stream_handler)
        name_row = ['Time']
        for mi_name, state_name in self.state_dict.items():
            for i_state in state_name:
                name_row.append(f"{mi_name}_{i_state}")
        self._state_stream_writer.writerow(name_row)

        # Create the buffer files
        for mi, i_buf in self._buffer_streaming_handle.items():
            for buf_name, v in i_buf.items():
                fn = self._bufferHandlerParam[mi][buf_name]['fn']
                fshape = self._bufferHandlerParam[mi][buf_name]['shape']
                if v[1] is None or v[1] == 'binary':
                    self._buffer_streaming_handle[mi][buf_name] = (open(fn, 'wb'), v[1])
                elif v[1] == 'movie':
                    self._buffer_streaming_handle[mi][buf_name] = (cv2.VideoWriter(fn, cv2.VideoWriter_fourcc(*'MJPG'),
                                                                                   int(1000 / self.refresh_interval),
                                                                                   fshape),
                                                                   'movie')
                else:
                    self._buffer_streaming_handle[mi][buf_name] = (None, None)

        start_time = self.get_timestamp()
        self._streaming_start_time = start_time
        self.streaming = True

    def _stop_streaming(self):
        if self.streaming:
            self.streaming = False
            self._state_stream_handler.close()
            for mi, i_buf in self._buffer_streaming_handle.items():
                for buf_name, v in i_buf.items():
                    if v[1] is None or v[1] == 'binary':
                        v[0].close()
                    elif v[1] == 'movie':
                        v[0].release()
                    else:
                        pass

            self._state_stream_fn = None
            self._state_stream_handler = None
            self._state_stream_writer = None
            self._buffer_handle_param = {}
            self._buffer_streaming_handle = {}
            self._streaming_start_time = 0
            self.streaming = False

    def _streaming(self):
        if self.streaming:
            # Write to state csv file
            trigger = True
            if self._trigger_state_name:
                mi, st = self._trigger_state_name.split('_')
                trigger_state = self.get_state_from(mi, st)
                if trigger_state is not None:
                    trigger = self.watch_state('Trigger', trigger_state)
            if trigger:
                t = self.get_timestamp() - self._streaming_start_time
                val_row = [t]
                for mi_name, state_name in self.state_dict.items():
                    state_dict = self.get_state_from(mi_name, 'ALL')
                    for i_state in state_name:
                        val_row.append(state_dict[i_state])
                self._state_stream_writer.writerow(val_row)

                for mi, i_buf in self._buffer_streaming_handle.items():
                    for buf_name, v in i_buf.items():
                        if v[1] is None or v[1] == 'binary':
                            self._buffer_streaming_handle[mi][buf_name].write(
                                bytearray(self.get_state_from(mi, buf_name)))
                        elif v[1] == 'movie':
                            self._buffer_streaming_handle[mi][buf_name].write(self.get_state_from(mi, buf_name))
                        else:
                            pass

    def get_timestamp(self):
        if self._ts_minion_name is not None:
            return self.get_state_from(self._ts_minion_name, 'timestamp') / 1000

        else:
            return time.perf_counter()

    def on_time(self, t):
        self._streaming_setup()
        self._streaming()
