import asyncio

import pytest

from autocurricula.core.memory.manager import MemoryManager
from autocurricula.core.orchestration.context import (
    STAGE_FETCH,
    STAGE_GRADE,
    STAGE_SYNC,
    FetchOutputs,
)
from autocurricula.core.orchestration.job_state import (
    JobRecord,
    JobStage,
    LocalCheckpointStore,
)
from autocurricula.schemas.grading import GradingBatchResult
from autocurricula.schemas.sis_sync import SISWriteResult

from .bench_fixtures import (
    SEATS,
    build_batch,
    build_bench_runner,
    build_event,
    stage_bench_batch,
)

pytestmark = pytest.mark.benchmark

JOB_COUNT = 40
BATCH_SIZE = 10


async def test_concurrent_batches_keep_session_state_isolated(
    settings, memory_manager: MemoryManager
) -> None:
    runner = build_bench_runner(settings, memory_manager)
    events = [build_event(index) for index in range(JOB_COUNT)]
    for index in range(JOB_COUNT):
        stage_bench_batch(settings, index)

    batches = (events[s : s + BATCH_SIZE] for s in range(0, JOB_COUNT, BATCH_SIZE))
    records: list[JobRecord] = []
    for chunk in batches:
        records.extend(await asyncio.gather(*(runner.process(e) for e in chunk)))

    assert len(records) == JOB_COUNT
    assert all(record.stage == JobStage.COMPLETED for record in records)
    assert all(record.error is None for record in records)
    every = {s.submission_id for i in range(JOB_COUNT) for s in build_batch(i).submissions}
    assert len(every) == JOB_COUNT * len(SEATS)

    store = LocalCheckpointStore(data_dir=settings.local_data_dir)
    for index, event in enumerate(events):
        batch = build_batch(index)
        expected_submissions = [item.submission_id for item in batch.submissions]
        expected_students = [item.student_id for item in batch.submissions]
        state = await store.load_state(event.job_id)
        assert state is not None
        assert state.job_id == event.job_id
        assert set(state.stage_statuses.values()) == {"succeeded"}
        fetch = FetchOutputs.model_validate(state.stage_results[STAGE_FETCH])
        assert [i.submission_id for i in fetch.batch.submissions] == expected_submissions
        grades = GradingBatchResult.model_validate(state.stage_results[STAGE_GRADE])
        assert [i.submission_id for i in grades.results] == expected_submissions
        sync = SISWriteResult.model_validate(state.stage_results[STAGE_SYNC])
        assert list(sync.per_record_statuses) == expected_students
        checkpoint = await store.get(event.job_id)
        assert checkpoint is not None
        assert checkpoint.stage == JobStage.COMPLETED
        assert checkpoint.event.job_id == event.job_id
