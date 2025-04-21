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
