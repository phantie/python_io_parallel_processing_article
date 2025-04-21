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
async def main(): ...


# This part will be omitted in further sections.
# We'll work on the *main* function.
if __name__ == "__main__":
    import asyncio

    # Turning the function "main" into a coroutine.
    coroutine = main()
    # Letting asyncio runtime execute your coroutine.
    asyncio.run(coroutine)
