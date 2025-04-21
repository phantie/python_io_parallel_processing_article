from io_processing.timeit import timer
from io_processing.task import normal_task

import asyncio


async def main():
    with timer():
        await normal_task(task_number=0, time_to_execute_in_seconds=1)
        # > processed task with task_number=0 time_to_execute_in_seconds=1 behavior=normal-sleep

    # > elapsed time: 1.00 seconds


if __name__ == "__main__":
    import asyncio

    coroutine = main()
    asyncio.run(coroutine)
