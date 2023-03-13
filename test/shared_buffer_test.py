import multiprocessing as mp
from multiprocessing import shared_memory
import numpy as np
import time

# Define a function for process A that reads the shared memory buffer
def read_buffer(name):
    # Attach to the existing shared memory block by name
    shm = shared_memory.SharedMemory(name=name)
    # Create a numpy array from the shared memory buffer
    arr = np.frombuffer(shm.buf, dtype=np.int32)
    # Loop until the first element is -1, indicating termination
    while arr[0] != -1:
        # Print the contents of the shared memory buffer
        print(f"Process A: {arr}")
        # Sleep for 1 second
        time.sleep(.001)
    # Close and unlink the shared memory block
    shm.close()
    shm.unlink()

# Define a function for process B that writes the shared memory buffer
def write_buffer(name):
    # Attach to the existing shared memory block by name
    shm = shared_memory.SharedMemory(name=name)
    # Create a numpy array from the shared memory buffer
    arr = np.ndarray((10,), dtype=np.int32, buffer=shm.buf)
    # Loop for 10 times
    for i in range(1000):
        # Write some random numbers to the shared memory buffer
        arr[:] = np.random.randint(0, 100, 10)
        # Print the contents of the shared memory buffer
        print(f"Process B: {arr}")
        # Sleep for 1 second
        time.sleep(.001)
    # Write -1 to the first element to signal termination
    arr[0] = -1
    # Close the shared memory block
    shm.close()

# Create a new shared memory block with a given name and size
if __name__ == '__main__':
    shm = shared_memory.SharedMemory(create=True, name="sharedBuffer", size=10)
    print(shm.size)
    # Create two processes that run the read and write functions with the shared memory name as argument
    p1 = mp.Process(target=read_buffer, args=("sharedBuffer",))
    p2 = mp.Process(target=write_buffer, args=("sharedBuffer",))
    # Start the processes
    p1.start()
    p2.start()
    # Wait for the processes to finish
    p1.join()
    p2.join()