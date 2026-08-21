from datetime import UTC, datetime
from pathlib import Path

from autocurricula.core.memory.manager import MemoryManager
from autocurricula.core.orchestration.job_state import JobStage
from autocurricula.core.resilience import (
    DLQ_KIND_SIS_WRITE,
    LocalDeadLetterStore,
    SyncOutageError,
    write_with_rollback,
)
from autocurricula.schemas.sis_sync import SISGradeRecord
from tests.orchestration.incident_fixtures import (
    ScriptedSISConnector,
    build_incident_runner,
    healthy_evaluator,
    roster,
    stage_roster,
    synced_records,
)
from tests.review.flow_stack import make_event, make_settings

JOB_ID = "job-sis-outage"
REJECTED = ("stu-002", "stu-005")


def written_ids(settings) -> list[str]:
    return sorted(record["student_id"] for record in synced_records(settings))


def grade_record(student_id: str) -> SISGradeRecord:
    return SISGradeRecord(
        student_id=student_id,
        subject="matematicas",
        score=3.0,
        percentage=75.0,
        feedback="graded",
        graded_at=datetime(2026, 8, 21, 12, 0, tzinfo=UTC),
    )


async def test_outage_parks_every_record_and_redelivery_writes_only_orphans(
    tmp_path: Path,
) -> None:
    settings = make_settings(tmp_path)
    memory_manager = MemoryManager.from_settings(settings)
    students = roster(6)
    stage_roster(settings, JOB_ID, students)
    dead_letter = LocalDeadLetterStore(settings.local_data_dir)
    connector = ScriptedSISConnector(settings.local_data_dir, outage=True)
    store = None

    def deliver():
        runner, opened = build_incident_runner(
            settings,
            memory_manager,
            healthy_evaluator(students),
            review_store=store,
            sis_connector=connector,
            dead_letter=dead_letter,
        )
        return runner, opened

    runner, store = deliver()
    outage_record = await runner.process(make_event(JOB_ID))

    assert outage_record.stage == JobStage.FAILED
    assert "sis unreachable" in (outage_record.error or "")
    parked = await dead_letter.list_pending(JOB_ID, DLQ_KIND_SIS_WRITE)
    assert sorted(entry.target for entry in parked) == sorted(students)
    assert all("sis unreachable" in entry.reason for entry in parked)
    assert all(entry.attempts == 0 for entry in parked)
    assert written_ids(settings) == []

    connector.outage = False
    connector.failing = set(REJECTED)
    runner, store = deliver()
    partial_record = await runner.process(make_event(JOB_ID))

    assert partial_record.stage == JobStage.FAILED
    assert connector.seen_targets[-1] == list(students)
    assert written_ids(settings) == sorted(set(students) - set(REJECTED))
    still_parked = await dead_letter.list_pending(JOB_ID, DLQ_KIND_SIS_WRITE)
    assert sorted(entry.target for entry in still_parked) == sorted(REJECTED)
    assert all(entry.attempts == 1 for entry in still_parked)

    connector.failing = set()
    runner, store = deliver()
    final_record = await runner.process(make_event(JOB_ID))

    assert final_record.stage == JobStage.COMPLETED
    assert connector.seen_targets[-1] == list(REJECTED)
    assert written_ids(settings) == sorted(students)
    assert await dead_letter.list_pending(JOB_ID, DLQ_KIND_SIS_WRITE) == []
    assert await dead_letter.list_exhausted(JOB_ID, DLQ_KIND_SIS_WRITE) == []


async def test_repeated_outages_never_exhaust_the_parked_orphans(
    tmp_path: Path,
) -> None:
    settings = make_settings(tmp_path)
    dead_letter = LocalDeadLetterStore(settings.local_data_dir)
    connector = ScriptedSISConnector(settings.local_data_dir, outage=True)
    students = roster(3)
    records = [grade_record(student) for student in students]

    async def attempt():
        return await write_with_rollback(
            job_id=JOB_ID,
            sis_connector=connector,
            records=records,
            quarantined_count=0,
            dead_letter=dead_letter,
            previous=None,
            max_attempts=3,
        )

    for _ in range(4):
        try:
            await attempt()
        except SyncOutageError as outage:
            assert outage.failed_ids == list(students)
            continue
        raise AssertionError("an outage must fail the sync stage")

    pending = await dead_letter.list_pending(JOB_ID, DLQ_KIND_SIS_WRITE)
    assert sorted(entry.target for entry in pending) == list(students)
    assert all(entry.attempts == 0 for entry in pending)
    assert await dead_letter.list_exhausted(JOB_ID, DLQ_KIND_SIS_WRITE) == []

    connector.outage = False
    result = await attempt()

    assert connector.seen_targets[-1] == list(students)
    assert result.failed_count == 0
    assert written_ids(settings) == list(students)
    assert await dead_letter.list_pending(JOB_ID, DLQ_KIND_SIS_WRITE) == []
