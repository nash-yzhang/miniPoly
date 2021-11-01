HIGH = 1
LOW = 0

max7219_reg_noop = 0x00
max7219_reg_digit0 = 0x01
max7219_reg_digit1 = 0x02
max7219_reg_digit2 = 0x03
max7219_reg_digit3 = 0x04
max7219_reg_digit4 = 0x05
max7219_reg_digit5 = 0x06
max7219_reg_digit6 = 0x07
max7219_reg_digit7 = 0x08
max7219_reg_decodeMode = 0x09
max7219_reg_intensity = 0x0a
max7219_reg_scanLimit = 0x0b
max7219_reg_shutdown = 0x0c
max7219_reg_displayTest = 0x0f


class LedMatrix:
    def __init__(self, board, dataIn, load, clock, maxInUse=1):
        self._board = board

        self.pins = dict()
        self.pins['dataIn'] = dataIn
        self.pins['load'] = load
        self.pins['clock'] = clock
        self.maxInUse = maxInUse

    def _digitalWrite(self, pin, val):
        self._board.digital[pin].write(val)

    def _putByte(self, data):
        for i in range(8, 0, -1):
            mask = 0x01 << (i - 1)
            self._digitalWrite(self.pins["clock"], LOW)
            if data & mask:
                self._digitalWrite(self.pins["dataIn"], HIGH)
            else:
                self._digitalWrite(self.pins["dataIn"], LOW)
            self._digitalWrite(self.pins["clock"], HIGH)

    def maxSingle(self, reg, col):
        self._digitalWrite(self.pins["load"], LOW)
        self._putByte(reg)
        self._putByte(col)
        self._digitalWrite(self.pins["load"], LOW)
        self._digitalWrite(self.pins["load"], HIGH)

    def maxAll(self, reg, col):
        self._digitalWrite(self.pins["load"], LOW)
        for _ in range(0, self.maxInUse):
            self._putByte(reg)
            self._putByte(col)
        self._digitalWrite(self.pins["load"], LOW)
        self._digitalWrite(self.pins["load"], HIGH)

    def maxOne(self, maxNr, reg, col):
        self._digitalWrite(self.pins["load"], LOW)

        for _ in range(self.maxInUse, maxNr, -1):
            self._putByte(0)
            self._putByte(0)

        self._putByte(reg)
        self._putByte(col)

        for _ in range(maxNr - 1, 0, -1):
            self._putByte(0)
            self._putByte(0)

        self._digitalWrite(self.pins["load"], LOW)
        self._digitalWrite(self.pins["load"], HIGH)

    def clear(self):
        for e in range(1, 9):
            self.maxAll(e, 0)

    def setup(self):
        print('Initializing _matrix...')
        self._digitalWrite(13, HIGH)
        self.maxAll(max7219_reg_scanLimit, 0x07)
        self.maxAll(max7219_reg_decodeMode, 0x00)
        self.maxAll(max7219_reg_shutdown, 0x01)
        self.maxAll(max7219_reg_displayTest, 0x00)
        self.clear()
        self.maxAll(max7219_reg_intensity, 0x01 & 0x0f)
        print('Done')

    def draw_matrix(self, point_matrix):
        for col, pointlist in enumerate(point_matrix):
            self.maxSingle(col + 1, int(''.join(str(int(v)) for v in pointlist), 2))









#
# from pymata_aio.pymata3 import PyMata3        # type: ignore
# from pymata_aio.constants import Constants    # type: ignore
#
# from PIL import Image
#
# MAX7219_REG_NOOP        = 0x00
# MAX7219_REG_DIGIT0      = 0x01
# MAX7219_REG_DIGIT1      = 0x02
# MAX7219_REG_DIGIT2      = 0x03
# MAX7219_REG_DIGIT3      = 0x04
# MAX7219_REG_DIGIT4      = 0x05
# MAX7219_REG_DIGIT5      = 0x06
# MAX7219_REG_DIGIT6      = 0x07
# MAX7219_REG_DIGIT7      = 0x08
# MAX7219_REG_DECODEMODE  = 0x09
# MAX7219_REG_INTENSITY   = 0x0a
# MAX7219_REG_SCANLIMIT   = 0x0b
# MAX7219_REG_SHUTDOWN    = 0x0c
# MAX7219_REG_DISPLAYTEST = 0x0f
#
# LOW, HIGH = 0, 1
# LSBFIRST, MSBFIRST = 0, 1
#
# # Following bit shifting functons adapted from https://wiki.python.org/moin/BitManipulation
#
#
# def test_bit(value: int, offset: int) -> int:
#     " Returns a 1, if the bit at 'offset' is one, else 0"
#     mask = 1 << offset
#     return 1 if (value & mask) else 0
#
#
# def set_bit(value: int, offset: int) -> int:
#     " Returns an integer with the bit at 'offset' set to 1"
#     mask = 1 << offset
#     return (value | mask)
#
#
# def clear_bit(value: int, offset: int) -> int:
#     " Returns an integer with the bit at 'offset' cleared "
#     mask = ~(1 << offset)
#     return (value & mask)
#
#
# def toggle_bit(value: int, offset: int) -> int:
#     " Returns an integer with the bit at 'offset' inverted, 0 -> 1 and 1 -> 0 "
#     mask = 1 << offset
#     return (value ^ mask)
#
#
# def write_bit(value: int, offset: int, bit: int) -> int:
#     if bit == HIGH:
#         return set_bit(value, offset)
#     elif bit == LOW:
#         return clear_bit(value, offset)
#     else:
#         raise Exception("bit must be high or low")
#
#
# class MaxMatrix:
#
#     def __init__(self, board, data_pin: int, load_pin: int, clock_pin: int):
#         self.board = board
#         self.data_pin = data_pin
#         self.load_pin = load_pin
#         self.clock_pin = clock_pin
#         self.buffer = bytearray(80)
#
#         # initialise the LED display
#         self.board.set_pin_mode(self.data_pin,  Constants.OUTPUT)
#         self.board.set_pin_mode(self.clock_pin,  Constants.OUTPUT)
#         self.board.set_pin_mode(self.load_pin,  Constants.OUTPUT)
#
#         self.board.digital_write(self.clock_pin, HIGH)
#
#         self.set_command(MAX7219_REG_SCANLIMIT, 0x07)
#         self.set_command(MAX7219_REG_DECODEMODE, 0x00)   # using an led matrix (not digits)
#         self.set_command(MAX7219_REG_SHUTDOWN, 0x01)     # not in shutdown mode
#         self.set_command(MAX7219_REG_DISPLAYTEST, 0x00)  # no display test
#
#         # empty registers, turn all LEDs off
#         self.clear()
#         self.set_intensity(0x0f)  # the first 0x0f is the value you can set
#
#     def reload(self) -> None:
#         for col in range(8):
#             self.board.digital_write(self.load_pin, LOW)
#             self.shift_out(col + 1)
#             self.shift_out(self.buffer[col])
#             self.board.digital_write(self.load_pin, LOW)
#             self.board.digital_write(self.load_pin, HIGH)
#
#     def clear(self):
#         self.buffer = bytearray(80)
#         self.reload()
#
#     def set_command(self, command: int, value: int):
#         self.board.digital_write(self.load_pin, LOW)
#
#         self.shift_out(command)
#         self.shift_out(value)
#
#         self.board.digital_write(self.load_pin, LOW)
#         self.board.digital_write(self.load_pin, HIGH)
#
#     def shift_out(self, value: int, bit_order: int=MSBFIRST):
#         # Adapted from hardware/arduino/avr/cores/arduino/wiring_shift.c
#         for i in range(8):
#             if bit_order == LSBFIRST:
#                 b = HIGH if ~~(value & (1 << i)) else LOW
#             else:
#                 b = HIGH if ~~(value & (1 << (7 - i))) else LOW
#             self.board.digital_write(self.data_pin, b)
#             self.board.digital_write(self.clock_pin, HIGH)
#             self.board.digital_write(self.clock_pin, LOW)
#
#     def set_intensity(self, intensity: int):
#         self.set_command(MAX7219_REG_INTENSITY, intensity)
#
#     def set_column(self, col: int, value: int):
#         """
#         set the column to the value, for example:
#         >>> mm.set_column(0, 0b11011001)
#         """
#         self.board.digital_write(self.load_pin, LOW)
#         self.shift_out(col + 1)
#         self.shift_out(value)
#         self.board.digital_write(self.load_pin, LOW)
#         self.board.digital_write(self.load_pin, HIGH)
#         self.buffer[col] = value
#
#     def set_row(self, row: int, value: int):
#         """
#         set the row to the value, for example:
#         >>> mm.set_row(0, 0b11011001)
#         """
#         for i in range(8):
#             b = test_bit(value, i)
#             self.buffer[i] = write_bit(self.buffer[i], row, b)
#         self.reload()
#
#     def set_dot(self, col: int, row: int, value: int):
#         self.buffer[col] = write_bit(self.buffer[col], row, value)
#         self.board.digital_write(self.load_pin, LOW)
#         self.shift_out(col + 1)
#         self.shift_out(self.buffer[col])
#         self.board.digital_write(self.load_pin, LOW)
#         self.board.digital_write(self.load_pin, HIGH)
#
#     def shift_left(self, fill_zero: bool = False):
#         if fill_zero:
#             self.buffer = self.buffer[-1:] + bytearray(1)
#         else:
#             self.buffer = self.buffer[-1:] + self.buffer[:-1]
#         self.reload()
#
#     def shift_right(self, fill_zero: bool = False):
#         if fill_zero:
#             self.buffer = self.buffer[1:] + bytearray(1)
#         else:
#             self.buffer = self.buffer[1:] + self.buffer[:1]
#         self.reload()
#
#     def shift_up(self, fill_zero: bool = False):
#         for i in range(len(self.buffer)):
#             if fill_zero:
#                 self.buffer[i] = self.buffer[i] << 1
#             else:
#                 self.buffer[i] = ((self.buffer[i] << 1) & 0xff) | test_bit(self.buffer[i], 7)
#         self.reload()
#
#     def shift_down(self, fill_zero = False):
#         for i in range(len(self.buffer)):
#             if fill_zero:
#                 self.buffer[i] = self.buffer[i] >> 1
#             else:
#                 self.buffer[i] = (self.buffer[i] >> 1) | (test_bit(self.buffer[i], 0) << 7)
#         self.reload()
#
#     def write_sprite(self, sprite: bytearray, x: int = 0, y: int = 0):
#         if x:
#             sprite = sprite[:]
#             for i in range(8):
#                 sprite[i] = sprite[i] >> x
#         self.buffer[y:y+8] = sprite
#         self.reload()
#
# def get_matrix(data, row, col):
#     m = []
#     for i in range(8):
#         m.append(data[((i+8*col)*128) + (row * 8): ((i+8*col) * 128) + (row * 8) + 8])
#     return m
#
#
# def make_sprite(matrix):
#     ba = bytearray(8)
#     for r in range(8):
#         for c in range(8):
#             bit = matrix[r][c]
#             ba[7 - c] = write_bit(ba[7 - c], 7 - r, bit)
#     return ba
#
