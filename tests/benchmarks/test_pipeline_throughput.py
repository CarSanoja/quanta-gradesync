import asyncio
import time

import pytest

from autocurricula.core.memory.manager import MemoryManager
from autocurricula.core.orchestration.job_state import (
    JobRecord,
    JobStage,
    LocalCheckpointStore,
)
from autocurricula.schemas.events import PubSubJobEvent

from .bench_fixtures import build_bench_runner, build_event, stage_bench_batch

pytestmark = pytest.mark.benchmark

JOB_COUNT = 50
MAX_CONCURRENT_JOBS = 10
THROUGHPUT_FLOOR = 20.0
WALL_LIMIT_SECONDS = 5.0


async def test_pipeline_processes_fifty_jobs_above_throughput_floor(
    settings, memory_manager: MemoryManager
) -> None:
    runner = build_bench_runner(settings, memory_manager)
    events = [build_event(index) for index in range(JOB_COUNT)]
    for index in range(JOB_COUNT):
        stage_bench_batch(settings, index)
    gate = asyncio.Semaphore(MAX_CONCURRENT_JOBS)

    async def run_one(event: PubSubJobEvent) -> JobRecord:
        async with gate:
            return await runner.process(event)

    started = time.perf_counter()
    records = await asyncio.gather(*(run_one(event) for event in events))
    elapsed = time.perf_counter() - started

    assert len(records) == JOB_COUNT
    assert all(record.stage == JobStage.COMPLETED for record in records)
    assert all(record.error is None for record in records)
    assert len({record.job_id for record in records}) == JOB_COUNT
    assert len(records) / elapsed >= THROUGHPUT_FLOOR
    assert elapsed < WALL_LIMIT_SECONDS

    store = LocalCheckpointStore(data_dir=settings.local_data_dir)
    persisted = await asyncio.gather(*(store.get(event.job_id) for event in events))
    assert all(
        item is not None and item.stage == JobStage.COMPLETED for item in persisted
    )
