# I/O bound parallel processing in python

When it comes to I/O [*asyncio*](https://pypi.org/project/asyncio/) is a must.

The state of modern python programming is to prefer an async library over sync
if it satisfies your needs because:

    - efficient resource utilization for I/O tasks
    - a lot easier to get right than with *multiprocessing*
    - asyncio.to_thread can turn an sync function to async by running it in a thread pool

The template for any async python program is:

```python
# entry point to your program.
# it's an asynchrnous function because it has "async" before "def main"
# a called asynchronous function turns into a "coroutine".
# a coroutine is a state machine which asyncio knows how handle,
# and nothing in the body gets ran until the asyncio runtime handles it
#
# from a practical standpoint, it can be awaited with "await" keyword inside async function
#
# an **important** thing to remember is that a blocking operation would block
# the whole runtime - so no other work will be done (no other coroutines will be further progressed in their executions)
# until that operation finishes
async def main():
    ...

# this part will be ommited in further section
# we'll work on *main* function
if __name__ == "__main__":
    import asyncio

    # turing the function "main" into a coroutine
    coroutine = main()
    # letting asyncio runtime to execute your coroutine
    asyncio.run(coroutine)

```

To showcase actual speed execution of further examples let's introduces a *timer* function

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

Default behavior of a task is to simulate work by sleeping.
Since it's customizable it would allow to generate many atypical scenarious.

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

Only 5 tasks but it's already getting annoying.

Let's parallelize them. We'll use *asyncio.gather* for it. 
It takes a list of coroutines and runs them in parallel.


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

    - I/0 bound task almost always are side effects - practically it would try to perform a DDOS attack on the services you interact with
    - a million coroutines is memory demanding
    - due to task switching of asyncio runtime the performance diminishes linearly relative to number of simultaneously ran coroutines

So there are problems to solve:

    - do not DDOS the services
    - keep memory usage acceptable
    - do not overload the asyncio runtime with too many simultaneous coroutines (it's not erlang/elixir)

The approach we'll take does not have a limit on tasks to process 1_000_000 * 1000 is ok too.

#### The approach

Producers put tasks in a queue. Consumers process the tasks.
I'll demonstrate an example with 1 producer and 50 consumers.

You probably don't want to hold a 1_000_000 parameters for tasks in memory simulateneously - you'd use lazy sequences.
For example you'd get results by pages (subsets) from database/api/etc.

Our first producer will produce tasks that don't fail, so our consumers can yet skip that part.

```python
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
            consumer_of_normal_tasks(task_queue) for consumer_number in range(CONSUMER_COUNT)
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
```

### Process unreliable tasks

Cases to handle:

    - timeouts
    - expected exceptions
    - wildcard exceptions

```python
import asyncio
import pydantic

POISON_PILL = object()


async def producer_of_unusual_tasks(task_queue: asyncio.Queue) -> None:
    # puts coroutines in the queue:
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

    # pretend that it's a stuck task
    unusually_long_to_execute_task_coroutine = normal_task(
        task_number=get_sequence_number(), time_to_execute_in_seconds=1000
    )
    await task_queue.put(unusually_long_to_execute_task_coroutine)

    # exception is specified in the docstring
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

    # to demonstrate/prove that wildcard exception handling is a must
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
    # the goal is to not let this consumer (worker) die or get stuck for too long
    #
    # for unusually_long_to_execute_task you

    while True:
        task = await task_queue.get()

        if task is POISON_PILL:
            await task_queue.put(POISON_PILL)
            task_queue.task_done()
            return

        while True:
            try:
                # asyncio.wait_for takes a coroutine and timeout value
                # and raises asyncio.TimeoutError if coroutine did not succeeded during the given time
                # so it solves unusually_long_to_execute_task
                await asyncio.wait_for(
                    task, timeout=10
                )  # for a real world it's a too small timeout
                break
            except asyncio.TimeoutError as e:
                # usually you would retry a few times with exponential backoff before giving up
                break
            except ValueError as e:
                # we know that task_that_raises_specified_exception raises this exception
                # so handle approriately
                break
            except Exception as e:
                # for such cases as task_that_raises_unspecified_exception_coro and
                # generally wild protection is a must
                #
                # I'd retry a few times before giving up
                break

        # after we've tried everything we could we mark it as done
        task_queue.task_done()


async def main():
    with timer():
        task_queue = asyncio.Queue()
        await asyncio.gather(
            producer_of_unusual_tasks(task_queue),
            consumer_of_unusual_tasks(task_queue),
            return_exceptions=True,  # much recommend
        )
        # > poison pill put in queue
        # > processed task with task_number=0 time_to_execute_in_seconds=1 behavior=normal-sleep

    # > elapsed time: 11.01 seconds

    # as a result we've handled common problems with event processing
    # and protected the consumers from dying/being stuck
```


### Auto adjust consumer number based on service availability/quotas 

Chapter TODO

## Further questions you might ask after implementing something like this:

    - What if the process crashes?
    - What if the process restarts?
    - Observability/alterting/logging?