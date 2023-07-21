# This script is to test arduino analog and digital port r/w frequency using pyfirmata
import pyfirmata as pf
from time import perf_counter,sleep
import numpy as np

# Set up the board
board = pf.Arduino('COM21')
print('Board is ready')

# Set up the pins
analog_input_pin = board.get_pin('a:0:i')
# Set up the variables
for i in range(10000):
    board.iterate()
    input = analog_input_pin.read()
    print(input)
    if i == 0:
        start_time = perf_counter()
print(f'{100*(perf_counter() - start_time)} ns')
board.exit()