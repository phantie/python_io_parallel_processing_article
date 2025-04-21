# entry point to your program
async def main(): ...


if __name__ == "__main__":
    import asyncio

    coroutine = (
        main()
    )  # turing the function "main" into a coroutine - something which can be "awaited"
    asyncio.run(coroutine)  # letting asyncio runtime to execute your coroutine
