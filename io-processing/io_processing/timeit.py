from contextlib import contextmanager
import time


@contextmanager
def timer():
    """
    Usage:
        >>> with timer():
        ...     # example: simulate a long-running operation
        ...     time.sleep(1)
        ...
        elapsed time: 1.00 seconds

    """
    start_time = time.time()
    try:
        yield
    finally:
        end_time = time.time()
        elapsed = end_time - start_time
        print(f"elapsed time: {elapsed:.2f} seconds")
