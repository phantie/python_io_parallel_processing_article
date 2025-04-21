# I/O Bound Parallel Processing in Python

When it comes to I/O, [*asyncio*](https://pypi.org/project/asyncio/) is a must.

The state of modern Python programming is to prefer an async library over sync if it satisfies your needs because:
```txt
- Efficient resource utilization for I/O tasks
- A lot easier to get right than with *multiprocessing*
- asyncio.to_thread can turn a sync function into async by running it in a thread pool
```
The template for any async Python program is:

```python
# Entry point to your program.
# It's an asynchronous function because it has "async" before "def main".
# A called asynchronous function turns into a "coroutine".
# A coroutine is a state machine that asyncio knows how to handle,
# and nothing in the body runs until the asyncio runtime handles it.
#
# From a practical standpoint, it can be awaited with the "await" keyword inside an async function.
#
# An **important** thing to remember is that a blocking operation would block
# the whole runtime - so no other work will be done (no other coroutines will make further progress in their executions)
# until that operation finishes.
async def main():
    ...

# This part will be omitted in further sections.
# We'll work on the *main* function.
if __name__ == "__main__":
    import asyncio

    # Turning the function "main" into a coroutine.
    coroutine = main()
    # Letting asyncio runtime execute your coroutine.
    asyncio.run(coroutine)
```

To showcase the actual speed of further examples, let's introduce a *timer* function:

```python
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
```

## The first task the examples will use:

```python
import asyncio
import pydantic

async def normal_task(
    task_number: pydantic.NonNegativeInt,
    time_to_execute_in_seconds: pydantic.NonNegativeFloat,
) -> None:
    await asyncio.sleep(time_to_execute_in_seconds)
    print(
        f"processed task with {task_number=!r} {time_to_execute_in_seconds=!r} behavior=normal-sleep"
    )
    return None
```

The default behavior of a task is to simulate work by sleeping.

## Let's solve problems

### Process 1 task

```python
async def main():
    with timer():
        await normal_task(task_number=0, time_to_execute_in_seconds=1)
        # > processed task with task_number=0 time_to_execute_in_seconds=1 behavior=normal-sleep

    # > elapsed time: 1.00 seconds
```

### Process 5 tasks

```python
async def main():
    with timer():
        for task_number in range(5):
            await normal_task(task_number=task_number, time_to_execute_in_seconds=1)
            # processed task with task_number=0 time_to_execute_in_seconds=1 behavior=normal-sleep
            # processed task with task_number=1 time_to_execute_in_seconds=1 behavior=normal-sleep
            # processed task with task_number=2 time_to_execute_in_seconds=1 behavior=normal-sleep
            # processed task with task_number=3 time_to_execute_in_seconds=1 behavior=normal-sleep
            # processed task with task_number=4 time_to_execute_in_seconds=1 behavior=normal-sleep

    # > elapsed time: 5.01 seconds
```

Only 5 tasks, but it's already getting annoying.

Let's parallelize them. We'll use *asyncio.gather* for it. It takes a list of coroutines and runs them in parallel.

```python
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
```

5 tasks done in just 1 second.

### Process 1_000_000 tasks

There are several problems if we take the previous approach with *asyncio.gather*:

    - I/O bound tasks almost always involve side effects - practically it would try to perform a DDOS attack on the services you interact with
    - A million coroutines is memory-demanding
    - Due to task switching of the asyncio runtime, performance diminishes linearly relative to the number of simultaneously running coroutines

So there are problems to solve:
```txt
- Do not DDOS the services
- Keep memory usage acceptable
- Do not overload the asyncio runtime with too many simultaneous coroutines (it's not Erlang/Elixir)
```

The approach we'll take does not have a limit on tasks to process. 1_000_000 * 1000 is okay too.

#### The approach

Producers put tasks in a queue. Consumers process the tasks. I'll demonstrate an example with 1 producer and 50 consumers.

You probably don't want to hold 1_000_000 parameters for tasks in memory simultaneously — you'd use lazy sequences. For example, you'd get results by pages (subsets) from a database/API/etc.

Our first producer will produce tasks that don't fail, so our consumers can skip that part for now.

```python
# Poison pill signifies that consumers should not wait for more tasks from a queue
POISON_PILL = object()

async def producer_of_normal_tasks(task_queue: asyncio.Queue, max_tasks: int) -> None:
    # Producer gets items from some source and puts coroutines in a queue
    for task_number in range(max_tasks):
        task = normal_task(task_number=task_number, time_to_execute_in_seconds=1)
        # When the queue is filled, the producer awaits free space.
        await task_queue.put(task)

    # Usually you would use a logger with info/warning level for this message
    print(f"poison pill put in queue")
    await task_queue.put(POISON_PILL)


async def consumer_of_normal_tasks(task_queue: asyncio.Queue):
    # Consumer perpetually gets items to process from the queue
    # and terminates upon a poison pill
    while True:
        task = await task_queue.get()

        if task is POISON_PILL:
            # Since the producer put only one instance of a poison pill
            # (the producer has no knowledge of consumer count)
            # each consumer will consume a poison pill
            # and put a new one for the next (possible) consumer
            await task_queue.put(POISON_PILL)
            task_queue.task_done()
            # No more tasks coming, so consumer must terminate
            return

        # Process the task
        await task
        # Specify that the task is done, so another consumer does not get it
        task_queue.task_done()


async def main():
    with timer():
        # Let's process 1_000 tasks with this approach (1_000_000 is too long to wait)
        TASKS_TO_PROCESS = 1000
        # Let's have 50 consumers
        CONSUMER_COUNT = 50

        # So what is the expected execution time?
        # 1 task = 1 second
        # 50 consumers have the processing power of 50 tasks per second
        # 1000 tasks / 50 tasks per second = 20 seconds
        # so 20 seconds

        task_queue = asyncio.Queue(
            # Depends, not a central point
            maxsize=CONSUMER_COUNT * 2,
        )

        # Generate consumer coroutines
        consumers = (
            consumer_of_normal_tasks(task_queue) for consumer_number in range(CONSUMER_COUNT)
        )

        the_producer = producer_of_normal_tasks(
            task_queue=task_queue,
            max_tasks=TASKS_TO_PROCESS,
        )

        # Start the produce-consume process
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

    # So we've got what we expected
```

### Process unreliable tasks

Cases to handle:
```txt
- Timeouts
- Expected exceptions
- Wildcard exceptions
```

```python
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
```

### Auto adjust consumer number based on service availability/quotas

Chapter TODO

## Further questions you might ask after implementing something like this:

```txt
- What if the process crashes?
- What if the process restarts?
- Observability/alerting/logging?
```

## Code repostory [Github](https://github.com/phantie/python_io_parallel_processing_article)