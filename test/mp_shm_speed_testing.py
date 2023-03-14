import multiprocessing as mp
import timeit
from multiprocessing import shared_memory

# Define a function that writes and reads a value from a shared object
def write_read(obj):
    obj.value = 42 # Write
    x = obj.value # Read

# Define a function that writes and reads an array from a shared object
def write_read_array(obj):
    obj[0] = 42 # Write
    x = obj[:] # Read

# Define a function that writes and reads a numpy array from a shared memory block
def write_read_numpy(obj):
    import numpy as np
    arr = np.ndarray((1,), dtype=np.int32, buffer=obj.buf) # Create a numpy array from the shared memory buffer
    arr[0] = 42 # Write
    x = arr[:] # Read

# Create a Value object
val = mp.Value('i', 0)

# Create an Array object
arr = mp.Array('i', 3)

# Create a SharedMemory object
shm = shared_memory.SharedMemory(create=True, size=12)

# Measure the time for 100000 write/read operations on the Value object
t1 = timeit.timeit(lambda: write_read(val), number=100000)
print(f"Time for Value: {t1:.6f} seconds")

# Measure the time for 100000 write/read operations on the Array object
t2 = timeit.timeit(lambda: write_read_array(arr), number=100000)
print(f"Time for Array: {t2:.6f} seconds")

# Measure the time for 100000 write/read operations on the SharedMemory object
t3 = timeit.timeit(lambda: write_read_numpy(shm), number=100000)
print(f"Time for SharedMemory: {t3:.6f} seconds")

# Close the shared memory block
shm.close()
shm.unlink()