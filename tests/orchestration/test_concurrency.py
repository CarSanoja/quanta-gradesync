import asyncio

from autocurricula.core.orchestration.concurrency import gather_limited


async def test_gather_limited_caps_in_flight_work_and_keeps_order() -> None:
    active = 0
    peak = 0

    async def job(index: int) -> int:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        active -= 1
        return index

    results = await gather_limited((job(i) for i in range(12)), limit=3)
    assert results == list(range(12))
    assert peak == 3


async def test_gather_limited_treats_nonpositive_limits_as_serial() -> None:
    order: list[int] = []

    async def job(index: int) -> int:
        order.append(index)
        await asyncio.sleep(0)
        return index

    assert await gather_limited([job(1), job(2)], limit=0) == [1, 2]
    assert order == [1, 2]
