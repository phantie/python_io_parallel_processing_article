from io_processing.timeit import timer
from io_processing.task import normal_task

import asyncio


async def main():
    with timer():
        coroutines = [
            normal_task(task_number=task_number, time_to_execute_in_seconds=1)
            for task_number in range(5)
        ]
        await asyncio.gather(*coroutines)

        # > processed task with task_number=0 time_to_execute_in_seconds=1 behavior=normal-sleep
        # > processed task with task_number=1 time_to_execute_in_seconds=1 behavior=normal-sleep
        # > processed task with task_number=2 time_to_execute_in_seconds=1 behavior=normal-sleep
        # > processed task with task_number=3 time_to_execute_in_seconds=1 behavior=normal-sleep
        # > processed task with task_number=4 time_to_execute_in_seconds=1 behavior=normal-sleep

    # > elapsed time: 1.00 seconds


if __name__ == "__main__":
    import asyncio

    coroutine = main()
    asyncio.run(coroutine)
