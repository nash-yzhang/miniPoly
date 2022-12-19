import pyfirmata
from pymata4 import pymata4
import time
from tkinter import *


def move_servo1(angle):
    pin8.write(angle)
    print(pinA5.read())

# def move_servo2(angle):
#     pin9.write(angle)

def main():
    global pin8, pinA5

    board = pyfirmata.Arduino('COM8')

    iter8 = pyfirmata.util.Iterator(board)
    iter8.start()

    pin8 = board.get_pin('d:8:s')
    # pin9 = board.get_pin('d:9:s')
    pinA5 = board.get_pin('a:4:o')

    root = Tk()
    scale_1 = Scale(root, command=move_servo1, to=180,
                  orient=HORIZONTAL, length=400, label='Servo 1 Angle')
    # scale_2 = Scale(root, command=move_servo2, to=180,
    #               orient=HORIZONTAL, length=400, label='Servo 2 Angle')
    scale_1.pack(anchor=CENTER)
    # scale_2.pack(anchor=CENTER)

    root.mainloop()

main()

# class DigitalInput:
#     """
#     Set a pin for digital input and received all data changes
#     in the callback method
#     """
#     def __init__(self, pin):
#         """
#         Set a pin as a digital input
#         :param pin: digital pin number
#         """
#
#         # Indices into the callback report data
#         self.init_time = time.time()
#         self.counter = 0
#
#         self.CB_PIN_MODE = 0
#         self.CB_PIN = 1
#         self.CB_VALUE = 2
#         self.CB_TIME = 3
#
#         # Instantiate this class with the pymata4 API
#         self.device = pymata4.Pymata4()
#
#         # Set the pin mode and specify the callback method.
#         self.device.set_pin_mode_analog_input(pin, callback=self.the_callback)
#
#         # Keep the program running and wait for callback events.
#         while time.time()-self.init_time < 10:
#             try:
#                 time.sleep(.0001)
#             # If user hits Control-C, exit cleanly.
#             except KeyboardInterrupt:
#                 self.device.shutdown()
#         print(time.time()-self.init_time)
#         print(self.counter)
#         self.device.shutdown()
#
#     def the_callback(self, data):
#         """
#         A callback function to report data changes.
#         This will print the pin number, its reported value
#         the pin type (digital, analog, etc.) and
#         the date and time when the change occurred
#
#         :param data: [pin, current reported value, pin_mode, timestamp]
#         """
#         # Convert the date stamp to readable format
#         date = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(data[self.CB_TIME]))
#         if self.counter == 0:
#             self.init_time = time.time()
#         self.counter += 1
#
#         # Print the pin, current value and time and date of the pin change event.
#         print(f'Pin: {data[self.CB_PIN]} Value: {data[self.CB_VALUE]} Time Stamp: {date}')
#
# if __name__ == '__main__':
#     # Monitor Pin 12 For Digital Input changes
#     DigitalInput(4)
