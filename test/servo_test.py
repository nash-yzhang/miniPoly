import pyfirmata
from tkinter import *


def move_servo1(angle):
    pin8.write(angle)

def move_servo2(angle):
    pin9.write(angle)


def main():
    global pin8, pin9

    board = pyfirmata.Arduino('COM4')

    iter8 = pyfirmata.util.Iterator(board)
    iter8.start()

    pin8 = board.get_pin('d:8:s')
    pin9 = board.get_pin('d:9:s')

    root = Tk()
    scale_1 = Scale(root, command=move_servo1, to=180,
                  orient=HORIZONTAL, length=400, label='Servo 1 Angle')
    scale_2 = Scale(root, command=move_servo2, to=180,
                  orient=HORIZONTAL, length=400, label='Servo 2 Angle')
    scale_1.pack(anchor=CENTER)
    scale_2.pack(anchor=CENTER)

    root.mainloop()


main()