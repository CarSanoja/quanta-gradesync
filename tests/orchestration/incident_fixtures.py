import json
from pathlib import Path

from autocurricula.agents.risk_detector import RiskDetector
from autocurricula.core.harness import BatchAnomalyBreaker
from autocurricula.core.memory.manager import MemoryManager
from autocurricula.core.orchestration.catalog import (
    MANIFEST_NAME,
    BatchManifest,
    LocalJobCatalog,
)
from autocurricula.core.orchestration.job_state import LocalCheckpointStore
from autocurricula.core.orchestration.runner import JobRunner
from autocurricula.core.resilience import DeadLetterStore
from autocurricula.core.review import LocalReviewStore
from autocurricula.schemas.exam import ExamBatch, ExamFile, ExamSubmission
from autocurricula.schemas.sis_sync import SISWriteRequest, SISWriteResult
from autocurricula.schemas.verification import VerificationReport
from autocurricula.tools.gcs_fetcher import LocalStagingFetcher
from autocurricula.tools.sis_connector import (
    SUCCESS_STATUSES,
    LocalSISConnector,
    SisWriteError,
)
from tests.orchestration.verifier_fixtures import ConfidenceMapEvaluator
from tests.review.flow_stack import (
    BUCKET,
    PREFIX,
    ScriptedAuditor,
    make_rubric,
    make_standard,
)


def roster(count: int) -> tuple[str, ...]:
    return tuple(f"stu-{index:03d}" for index in range(1, count + 1))


def staged_root(settings) -> Path:
    return settings.gcs_local_staging_dir / BUCKET / PREFIX


def stage_roster(
    settings, job_id: str, students: tuple[str, ...], extra_files: tuple[str, ...] = ()
) -> None:
    batch = ExamBatch(
        job_id=job_id,
        class_id="10A",
        subject="matematicas",
        grade_level="grade-8",
        rubric_id="rub-flow-1",
        submissions=[
            ExamSubmission(
                submission_id=student,
                student_id=student,
                files=[
                    ExamFile(
                        gcs_uri=f"gs://{BUCKET}/{PREFIX}/{student}.jpg",
                        mime_type="image/jpeg",
                        page_count=1,
                    )
                ],
            )
            for student in students
        ],
    )
    manifest = BatchManifest(
        batch=batch, rubric=make_rubric(), curriculum_standard=make_standard()
    )
    root = staged_root(settings)
    root.mkdir(parents=True, exist_ok=True)
    (root / MANIFEST_NAME).write_text(manifest.model_dump_json(), encoding="utf-8")
    for student in students:
        (root / f"{student}.jpg").write_bytes(b"scan")
    for name in extra_files:
        (root / name).write_bytes(b"late scan")


class CrashingEvaluator:
    def __init__(self, healthy: tuple[str, ...], confidence: float = 0.95) -> None:
        self._healthy = set(healthy)
        self._delegate = ConfidenceMapEvaluator(
            {student: confidence for student in healthy}
        )

    async def grade(self, submission, rubric, context):
        if submission.student_id not in self._healthy:
            raise RuntimeError(f"grader crashed for {submission.student_id}")
        return await self._delegate.grade(submission, rubric, context)


def healthy_evaluator(students: tuple[str, ...], confidence: float = 0.95):
    return ConfidenceMapEvaluator({student: confidence for student in students})


class ScriptedSISConnector:
    def __init__(
        self, data_dir: Path, *, outage: bool = False, failing: tuple[str, ...] = ()
    ) -> None:
        self._delegate = LocalSISConnector(data_dir=data_dir)
        self.outage = outage
        self.failing = set(failing)
        self.seen_targets: list[list[str]] = []

    async def write_grades(self, request: SISWriteRequest) -> SISWriteResult:
        self.seen_targets.append([record.student_id for record in request.records])
        if self.outage:
            raise SisWriteError("ConnectError: All connection attempts failed")
        accepted = [
            record
            for record in request.records
            if record.student_id not in self.failing
        ]
        statuses = {
            record.student_id: "error:HTTP_500"
            for record in request.records
            if record.student_id in self.failing
        }
        if accepted:
            written = await self._delegate.write_grades(
                SISWriteRequest(job_id=request.job_id, records=accepted)
            )
            statuses.update(written.per_record_statuses)
        succeeded = sum(1 for status in statuses.values() if status in SUCCESS_STATUSES)
        return SISWriteResult(
            job_id=request.job_id,
            per_record_statuses=statuses,
            succeeded_count=succeeded,
            failed_count=len(statuses) - succeeded,
        )


def build_incident_runner(
    settings,
    memory_manager: MemoryManager,
    evaluator,
    *,
    review_store: LocalReviewStore | None = None,
    checkpoint_dir: Path | None = None,
    breaker: BatchAnomalyBreaker | None = None,
    verify_max_iterations: int = 0,
    sis_connector=None,
    dead_letter: DeadLetterStore | None = None,
) -> tuple[JobRunner, LocalReviewStore]:
    store = review_store or LocalReviewStore(data_dir=settings.local_data_dir)
    runner = JobRunner(
        memory_manager=memory_manager,
        fetcher=LocalStagingFetcher(staging_dir=settings.gcs_local_staging_dir),
        grading_evaluator=evaluator,
        auditor=ScriptedAuditor(),
        risk_detector=RiskDetector(),
        sis_connector=(
            sis_connector
            if sis_connector is not None
            else LocalSISConnector(data_dir=settings.local_data_dir)
        ),
        checkpoint_store=LocalCheckpointStore(
            data_dir=checkpoint_dir or settings.local_data_dir
        ),
        catalog=LocalJobCatalog(staging_dir=settings.gcs_local_staging_dir),
        review_store=store,
        sis_breaker=breaker,
        verify_max_iterations=verify_max_iterations,
        dead_letter=dead_letter,
    )
    return runner, store


async def verification_report(settings, job_id: str, checkpoint_dir: Path | None = None):
    store = LocalCheckpointStore(data_dir=checkpoint_dir or settings.local_data_dir)
    state = await store.load_state(job_id)
    return VerificationReport.model_validate(state.stage_results["verify"])


def synced_records(settings) -> list[dict]:
    path = settings.local_data_dir / "sis_writes.jsonl"
    if not path.is_file():
        return []
    records: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        records.extend(json.loads(line)["request"]["records"])
    return records
