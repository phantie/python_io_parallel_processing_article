from io_processing.timeit import timer
from io_processing.task import normal_task

import asyncio
import pydantic

POISON_PILL = object()


async def producer_of_unusual_tasks(task_queue: asyncio.Queue) -> None:
    # Puts coroutines in the queue:
    #   - normal_task
    #   - unusually_long_to_execute_task
    #   - task_that_raises_specified_exception
    #   - task_that_raises_unspecified_exception

    def get_sequence_number_generator():
        number = 0
        while True:
            yield number
            number += 1

    sequence_number_generator = get_sequence_number_generator()
    get_sequence_number = lambda: next(sequence_number_generator)

    normal_task_coroutine = normal_task(
        task_number=get_sequence_number(), time_to_execute_in_seconds=1
    )
    await task_queue.put(normal_task_coroutine)

    # Pretend that it's a stuck task
    unusually_long_to_execute_task_coroutine = normal_task(
        task_number=get_sequence_number(), time_to_execute_in_seconds=1000
    )
    await task_queue.put(unusually_long_to_execute_task_coroutine)

    # Exception is specified in the docstring
    async def task_that_raises_specified_exception(
        task_number: pydantic.NonNegativeInt,
    ):
        """
        Raises:
            ValueError: Always raised when the function is called.
        """
        raise ValueError

    task_that_raises_specified_exception_coro = task_that_raises_specified_exception(
        task_number=get_sequence_number()
    )
    await task_queue.put(task_that_raises_specified_exception_coro)

    # To demonstrate/prove that wildcard exception handling is a must
    # for consumer coroutine protection
    async def task_that_raises_unspecified_exception(
        task_number: pydantic.NonNegativeInt,
    ) -> None:
        raise ZeroDivisionError("did not expect that?")

    task_that_raises_unspecified_exception_coro = (
        task_that_raises_unspecified_exception(task_number=get_sequence_number())
    )
    await task_queue.put(task_that_raises_unspecified_exception_coro)

    print(f"poison pill put in queue")
    await task_queue.put(POISON_PILL)


async def consumer_of_unusual_tasks(task_queue: asyncio.Queue):
    # The goal is to not let this consumer (worker) die or get stuck for too long
    #
    # For the unusually_long_to_execute_task, you

    while True:
        task = await task_queue.get()

        if task is POISON_PILL:
            await task_queue.put(POISON_PILL)
            task_queue.task_done()
            return

        while True:
            try:
                # asyncio.wait_for takes a coroutine and a timeout value
                # and raises asyncio.TimeoutError if the coroutine did not succeed during the given time,
                # so it solves unusually_long_to_execute_task
                await asyncio.wait_for(
                    task, timeout=10
                )  # In a real world scenario, 10 seconds might be too short
                break
            except asyncio.TimeoutError as e:
                # Usually you would retry a few times with exponential backoff before giving up
                break
            except ValueError as e:
                # We know that task_that_raises_specified_exception raises this exception
                # so handle appropriately
                break
            except Exception as e:
                # For such cases as task_that_raises_unspecified_exception_coro and
                # generally wild protection is a must
                #
                # I'd retry a few times before giving up
                break

        # After we've tried everything we could, we mark it as done
        task_queue.task_done()


async def main():
    with timer():
        task_queue = asyncio.Queue()
        await asyncio.gather(
            producer_of_unusual_tasks(task_queue),
            consumer_of_unusual_tasks(task_queue),
            return_exceptions=True,  # much recommended
        )
        # > poison pill put in queue
        # > processed task with task_number=0 time_to_execute_in_seconds=1 behavior=normal-sleep

    # > elapsed time: 11.01 seconds

    # As a result, we've handled common problems with event processing
    # and protected the consumers from dying/being stuck


if __name__ == "__main__":
    import asyncio

    coroutine = main()
    asyncio.run(coroutine)
