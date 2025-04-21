from io_processing.timeit import timer
from io_processing.task import normal_task

import asyncio

# poison pill signifies that consumers should not wait for more tasks from a queue
POISON_PILL = object()


async def producer_of_normal_tasks(task_queue: asyncio.Queue, max_tasks: int) -> None:
    # producer gets items from some source and puts coroutines in a queue
    for task_number in range(max_tasks):
        task = normal_task(task_number=task_number, time_to_execute_in_seconds=1)
        # when the queue is filled, the producer awaits for free space.
        await task_queue.put(task)

    # usually you would use logger with info/warning level for this message
    print(f"poison pill put in queue")
    await task_queue.put(POISON_PILL)


async def consumer_of_normal_tasks(task_queue: asyncio.Queue):
    # consumer perpetually gets items to process from a queue
    # and terminates for a poison pill
    while True:
        task = await task_queue.get()

        if task is POISON_PILL:
            # since the producer did put only one instance of a poison pill
            # (the producer has no knowledge of consumer count)
            # each consumer will consume a poison pill
            # and put a new one for the next (possible) consumer
            await task_queue.put(POISON_PILL)
            task_queue.task_done()
            # no more tasks coming so consumer must terminate
            return

        # process the task
        await task
        # specify that the task is done, so other consumer does not get it later
        task_queue.task_done()


async def main():
    with timer():
        # let's process 1_000 tasks with this approach (1_000_000 is to long to wait)
        TASKS_TO_PROCESS = 1000
        # let's have 50 consumers
        CONSUMER_COUNT = 50

        # so what is the expected execution time?
        # 1 task = 1 second
        # 50 consumers have processing power of 50 tasks per second
        # 1000 tasks / 50 tasks per second = 20 seconds
        # so 20 seconds

        task_queue = asyncio.Queue(
            # depends, not a central point
            maxsize=CONSUMER_COUNT
            * 2,
        )

        # generate consumers coroutines
        consumers = (
            consumer_of_normal_tasks(task_queue)
            for consumer_number in range(CONSUMER_COUNT)
        )

        the_producer = producer_of_normal_tasks(
            task_queue=task_queue,
            max_tasks=TASKS_TO_PROCESS,
        )

        # start produce-consume process
        await asyncio.gather(
            the_producer,
            *consumers,
        )
        # > processed task with task_number=0 time_to_execute_in_seconds=1 behavior=normal-sleep
        # > ...
        # > processed task with task_number=849 time_to_execute_in_seconds=1 behavior=normal-sleep
        # > poison pill put in queue
        # > processed task with task_number=850 time_to_execute_in_seconds=1 behavior=normal-sleep
        # > ...
        # > processed task with task_number=999 time_to_execute_in_seconds=1 behavior=normal-sleep

    # > elapsed time: 20.04 seconds

    # so we've got what we expected


if __name__ == "__main__":
    import asyncio

    coroutine = main()
    asyncio.run(coroutine)
