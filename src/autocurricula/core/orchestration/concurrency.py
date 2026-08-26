import asyncio
from collections.abc import Awaitable, Iterable

DEFAULT_MODEL_CONCURRENCY = 8


async def gather_limited[T](awaitables: Iterable[Awaitable[T]], limit: int) -> list[T]:
    semaphore = asyncio.Semaphore(max(1, limit))

    async def guarded(awaitable: Awaitable[T]) -> T:
        async with semaphore:
            return await awaitable

    return list(await asyncio.gather(*(guarded(item) for item in awaitables)))
