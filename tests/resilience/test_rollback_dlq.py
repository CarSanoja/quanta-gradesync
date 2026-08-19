from pathlib import Path

from autocurricula.agents.risk_detector import RiskDetector
from autocurricula.core.memory.manager import MemoryManager
from autocurricula.core.orchestration.catalog import LocalJobCatalog
from autocurricula.core.orchestration.job_state import (
    JobStage,
    LocalCheckpointStore,
)
from autocurricula.core.orchestration.runner import JobRunner
from autocurricula.core.resilience import (
    DeadLetterStatus,
    LocalDeadLetterStore,
    SyncPartialError,
    write_with_rollback,
)
from autocurricula.core.review import LocalReviewStore
from autocurricula.schemas.sis_sync import SISGradeRecord, SISWriteResult
from autocurricula.tools.gcs_fetcher import LocalStagingFetcher
from tests.orchestration.verifier_fixtures import ConfidenceMapEvaluator
from tests.review.flow_stack import (
    STUDENTS,
    ScriptedAuditor,
    make_event,
    make_settings,
    stage_batch,
)
import json
from datetime import datetime, timezone

from autocurricula.tools.sis_connector import LocalSISConnector


def _record(student_id: str) -> SISGradeRecord:
    graded_at = datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)
    return SISGradeRecord(
        student_id=student_id,
        subject="matematicas",
        score=3.0,
        percentage=75.0,
        feedback="ok",
        graded_at=graded_at,
    )


class PartialConnector:
    def __init__(self, failing: set[str], delegate: LocalSISConnector) -> None:
        self._failing = failing
        self._delegate = delegate
        self.seen_targets: list[list[str]] = []

    async def write_grades(self, request) -> SISWriteResult:
        from autocurricula.schemas.sis_sync import SISWriteRequest

        self.seen_targets.append([record.student_id for record in request.records])
        accepted = [
            record
            for record in request.records
            if record.student_id not in self._failing
        ]
        statuses = {
            record.student_id: "error:HTTP_500"
            for record in request.records
            if record.student_id in self._failing
        }
        job_id = request.job_id
        if accepted:
            result = await self._delegate.write_grades(
                SISWriteRequest(job_id=job_id, records=accepted)
            )
            statuses.update(result.per_record_statuses)
        succeeded = sum(1 for status in statuses.values() if "error" not in status)
        return SISWriteResult(
            job_id=job_id,
            per_record_statuses=statuses,
            succeeded_count=succeeded,
            failed_count=len(statuses) - succeeded,
        )


async def test_partial_failure_records_orphans_and_retry_only_orphans(
    tmp_path: Path,
) -> None:
    settings = make_settings(tmp_path)
    dead_letter = LocalDeadLetterStore(settings.local_data_dir)
    delegate = LocalSISConnector(data_dir=settings.local_data_dir)
    connector = PartialConnector(failing={"stu-002"}, delegate=delegate)
    records = [_record(student) for student in STUDENTS]

    try:
        await write_with_rollback(
            job_id="job-rb",
            sis_connector=connector,
            records=records,
            quarantined_count=0,
            dead_letter=dead_letter,
            previous=None,
            max_attempts=3,
        )
    except SyncPartialError as partial:
        assert partial.failed_ids == ["stu-002"]
        assert "stu-001" in partial.merged.per_record_statuses
        previous = partial.merged
    else:
        raise AssertionError("partial failure must raise")

    pending = await dead_letter.list_pending("job-rb", "sis_write")
    assert [entry.target for entry in pending] == ["stu-002"]
    assert pending[0].attempts == 1

    connector._failing = set()
    result = await write_with_rollback(
        job_id="job-rb",
        sis_connector=connector,
        records=records,
        quarantined_count=0,
        dead_letter=dead_letter,
        previous=previous,
        max_attempts=3,
    )

    assert connector.seen_targets[-1] == ["stu-002"]
    assert result.failed_count == 0
    assert set(result.per_record_statuses) == set(STUDENTS)
    assert await dead_letter.list_pending("job-rb", "sis_write") == []


async def test_exhausted_orphans_are_never_retried(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    dead_letter = LocalDeadLetterStore(settings.local_data_dir)
    delegate = LocalSISConnector(data_dir=settings.local_data_dir)
    connector = PartialConnector(failing={"stu-002"}, delegate=delegate)
    records = [_record(student) for student in STUDENTS]

    for _ in range(3):
        try:
            await write_with_rollback(
                job_id="job-x",
                sis_connector=connector,
                records=records,
                quarantined_count=0,
                dead_letter=dead_letter,
                previous=None,
                max_attempts=3,
            )
        except SyncPartialError:
            continue

    exhausted = await dead_letter.list_exhausted("job-x", "sis_write")
    assert [entry.target for entry in exhausted] == ["stu-002"]
    assert exhausted[0].attempts == 3

    connector._failing = set()
    result = await write_with_rollback(
        job_id="job-x",
        sis_connector=connector,
        records=records,
        quarantined_count=0,
        dead_letter=dead_letter,
        previous=None,
        max_attempts=3,
    )

    assert connector.seen_targets[-1] == ["stu-001", "stu-003"]
    assert "stu-002" not in result.per_record_statuses
    assert result.failed_count == 0


async def test_end_to_end_resume_retries_only_orphans(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    memory_manager = MemoryManager.from_settings(settings)
    delegate = LocalSISConnector(data_dir=settings.local_data_dir)
    failing = PartialConnector(failing={"stu-002"}, delegate=delegate)

    def build_runner(connector) -> JobRunner:
        return JobRunner(
            memory_manager=memory_manager,
            fetcher=LocalStagingFetcher(staging_dir=settings.gcs_local_staging_dir),
            grading_evaluator=ConfidenceMapEvaluator(
                {student: 0.95 for student in STUDENTS}
            ),
            auditor=ScriptedAuditor(),
            risk_detector=RiskDetector(),
            sis_connector=connector,
            checkpoint_store=LocalCheckpointStore(data_dir=settings.local_data_dir),
            catalog=LocalJobCatalog(staging_dir=settings.gcs_local_staging_dir),
            review_store=LocalReviewStore(data_dir=settings.local_data_dir),
            dead_letter=LocalDeadLetterStore(settings.local_data_dir),
            dead_letter_max_attempts=3,
        )

    stage_batch(settings, "job-resume")
    event = make_event("job-resume")

    failed_record = await build_runner(failing).process(event)
    assert failed_record.stage == JobStage.FAILED

    failing._failing = set()
    completed = await build_runner(failing).process(event)

    assert completed.stage == JobStage.COMPLETED
    lines = (settings.local_data_dir / "sis_writes.jsonl").read_text(
        encoding="utf-8"
    ).splitlines()
    written = [
        record["student_id"]
        for line in lines
        for record in json.loads(line)["request"]["records"]
    ]
    assert written.count("stu-002") == 1
    assert sorted(written) == sorted(STUDENTS)
    audit_path = settings.local_data_dir / "audit" / "job-resume.jsonl"
    assert not audit_path.exists()
