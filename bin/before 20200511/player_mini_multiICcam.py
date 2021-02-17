<<<<<<< Updated upstream:player/player_mini_multiICcam.py
import os
import sys
sys.path.insert(1,os.getcwd())
from Glimgui.GlImgui import glimWindow,glimManager
from glumpy import app
from pyfirmata import Arduino, util
import serial.tools.list_ports
from minipoly import miniPoly as mnp
from glumpy.app import clock
from time import time

def main(arduino_conn):
    GIM = glimManager()
    config = app.configuration.Configuration()
    config.stencil_size = 8
    glimgui_win = glimWindow(1024,720,config = config,minion_plug=arduino_conn)
    GIM.register_windows(glimgui_win)
    glimgui_win.set_sti_module('mini_multiICcam')
    GIM.run()


def arduino_IO(glim_conn):
    myclock = clock.Clock()
    myclock.set_fps_limit(1000)

    ports = list(serial.tools.list_ports.comports())
    Arduino_COM_Name = [p[0] for p in ports if 'COM' in p.__str__()][0]
    arduino_board = Arduino(Arduino_COM_Name)
    arduino_iterator = util.Iterator(arduino_board)
    arduino_iterator.start()
    LED_pin = arduino_board.get_pin('d:11:p')
    arduino_board.analog[0].enable_reporting()

    stayalive = True
    should_record = False
    recording = False
    timeline_file_name = ''
    timeline_file = None
    stimulus_frame_n = -1
    a = 0
    while stayalive:
        glim_conn.get('glim', ['_isalive','LED_power','rec_on','vid_fn','_frame_count'])
        if '_isalive' in glim_conn.inbox.keys():
            stayalive = glim_conn.inbox['_isalive']

        if 'LED_power' in glim_conn.inbox.keys():
            LED_pin.write(glim_conn.inbox['LED_power'])

        if 'rec_on' in glim_conn.inbox.keys():
            should_record = glim_conn.inbox['rec_on']

        if 'vid_fn' in glim_conn.inbox.keys():
            timeline_file_name = glim_conn.inbox['vid_fn']

        if '_frame_count' in glim_conn.inbox.keys():
            stimulus_frame_n = glim_conn.inbox['_frame_count']


        internal_timestamp = int(time()*1000)
        ai = arduino_board.analog[0].read()
        if ai:
            analog_sig = int(ai*1000)
        else:
            analog_sig = -1
        glim_conn.put(locals(), ['internal_timestamp', 'analog_sig'])

        if should_record and not recording:
            if timeline_file_name:
                timeline_file = open(timeline_file_name[:-3] + 'txt', 'w')
                recording = True
            else:
                print("ERROR: Empty timeline file name")
        elif recording and not should_record:
            if timeline_file:
                timeline_file.close()
                recording = False

        if recording:
            if timeline_file:
                timeline_msg = '%d %d %d\n' % (internal_timestamp, stimulus_frame_n, analog_sig)
                timeline_file.write(timeline_msg)
            else:
                print("ERROR: Cannot write timeline to non-existing file")

        glim_conn.give('glim', ['internal_timestamp','analog_sig'])

    #Terminating paragraph
    try:
        arduino_board.exit()
    except:
        print(
            "\033[1;31mERROR: \033[0;33m An error occurred when disconnecting \033[0m[\033[1;31m arduino_board \033[0m]")





if __name__ == '__main__' :
    minion_manager = mnp.manager()
    minion_manager.add_minion('glim', main)
    minion_manager.add_minion('arduino_IO', arduino_IO)
    minion_manager.add_queue_connection('glim<->arduino_IO')
    minion_manager.run('all')
=======
import os, sys

__rootpath__ = 'C:\\Users\\yzhang\\Desktop\\miniPoly-v0.3'
os.chdir(__rootpath__)
dll_path = __rootpath__ + '\\dll'
os.environ['PATH'] = dll_path + os.pathsep + os.environ['PATH']
sys.path.insert(0, __rootpath__)

from bin.GlImgui import glimWindow
from glumpy import app
from pyfirmata import Arduino, util
import serial.tools.list_ports
import bin.miniPoly as mnp
from glumpy.app import clock
from time import time


def arduino_io(hook):
    myclock = clock.Clock()
    myclock.set_fps_limit(1000)

    ports = list(serial.tools.list_ports.comports())
    Arduino_COM_Name = [p[0] for p in ports if 'COM' in p.__str__()][0]
    arduino_board = Arduino(Arduino_COM_Name)
    arduino_iterator = util.Iterator(arduino_board)
    arduino_iterator.start()
    LED_pin = arduino_board.get_pin('d:11:p')
    arduino_board.analog[0].enable_reporting()

    isrunning = True
    should_record = False
    timeline_file_name = ''
    stimulus_frame_n = -1
    LED_power = 0.

    timeline_file = None
    isrecording = False

    a = 0
    print('\nArduino connected\n')
    hook.put({'ard_conn':True})
    hook.give('glim',['ard_conn'])
    while isrunning:
        hook.get('glim')

        if 'should_run' in hook.inbox.keys():
            isrunning = hook.inbox['should_run']
            hook._isrunning = isrunning

        if 'LED_power' in hook.inbox.keys():
            LED_pin.write(hook.inbox['LED_power'])

        if 'rec_on' in hook.inbox.keys():
            should_record = hook.inbox['rec_on']

        if 'vid_fn' in hook.inbox.keys():
            timeline_file_name = hook.inbox['vid_fn']

        if '_frame_count' in hook.inbox.keys():
            stimulus_frame_n = hook.inbox['_frame_count']

        # print('should record: ',should_record)

        internal_timestamp = int(time() * 1000)
        ai = arduino_board.analog[0].read()
        if ai:
            analog_sig = int(ai * 1000)
        else:
            analog_sig = -1
        hook.put(locals(), ['internal_timestamp', 'analog_sig'])

        if should_record and not isrecording:
            if timeline_file_name:
                timeline_file = open(timeline_file_name[:-3] + 'txt', 'w')
                isrecording = True
            else:
                print("ERROR: Empty timeline file name")
        elif isrecording and not should_record:
            if timeline_file:
                timeline_file.close()
                isrecording = False

        if isrecording:
            if timeline_file:
                timeline_msg = '%d %d %d\n' % (internal_timestamp, stimulus_frame_n, analog_sig)
                timeline_file.write(timeline_msg)
            else:
                print("ERROR: Cannot write timeline to non-existing file")

        hook.give('glim', ['internal_timestamp', 'analog_sig'])

    # Terminating paragraph
    try:
        arduino_board.exit()
    except:
        print(
            "\033[1;31mERROR: \033[0;33m An error occurred when disconnecting \033[0m[\033[1;31m arduino_board \033[0m]")


def functest1(hook):
    #     # GIM = glimManager()
    config = app.configuration.Configuration()
    glimgui_win = glimWindow(hook._name, 1024, 720, config=config, minion_plug=hook)
    glimgui_win.import_sti_module('stimulus.mini_multiICcam')
    glimgui_win.set_sti_module(essential_func_name=['prepare', 'set_widgets'], draw_func_name=None)
    glimgui_win.run()


if __name__ == '__main__':
    minion_manager = mnp.manager()
    minion_manager.add_minion('glim', functest1)
    minion_manager.add_minion('arduino_IO', arduino_io)
    minion_manager.add_queue_connection('glim<->arduino_IO')
    minion_manager.run('all')
>>>>>>> Stashed changes:bin/before 20200511/player_mini_multiICcam.py
