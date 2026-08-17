import json
from pathlib import Path

from autocurricula.agents.risk_detector import RiskDetector
from autocurricula.core.harness import BatchAnomalyBreaker
from autocurricula.core.memory.manager import MemoryManager
from autocurricula.core.orchestration.catalog import LocalJobCatalog
from autocurricula.core.orchestration.job_state import (
    JobStage,
    LocalCheckpointStore,
)
from autocurricula.core.orchestration.runner import JobRunner
from autocurricula.core.orchestration.verifier import DEFAULT_VERIFY_MAX_ITERATIONS
from autocurricula.core.review import LocalReviewStore
from autocurricula.schemas.grading import GradingResult
from autocurricula.tools.gcs_fetcher import LocalStagingFetcher
from autocurricula.tools.sis_connector import LocalSISConnector
from tests.orchestration.verifier_fixtures import (
    ConfidenceMapEvaluator,
    verification_report,
)
from tests.review.flow_stack import (
    BUCKET,
    PREFIX,
    STUDENTS,
    ScriptedAuditor,
    make_event,
    make_settings,
    stage_batch,
    written_students,
)


class ExplodingEvaluator(ConfidenceMapEvaluator):
    def __init__(self, confidence_by_student, explode_for: set[str]) -> None:
        super().__init__(confidence_by_student)
        self._explode_for = explode_for

    async def grade(self, submission, rubric, context) -> GradingResult:
        if submission.student_id in self._explode_for:
            raise RuntimeError("simulated runaway reasoning loop")
        return await super().grade(submission, rubric, context)


def build_harness_runner(
    settings,
    memory_manager: MemoryManager,
    primary,
    *,
    breaker: BatchAnomalyBreaker | None = None,
) -> JobRunner:
    review_store = LocalReviewStore(data_dir=settings.local_data_dir)
    return JobRunner(
        memory_manager=memory_manager,
        fetcher=LocalStagingFetcher(staging_dir=settings.gcs_local_staging_dir),
        grading_evaluator=primary,
        auditor=ScriptedAuditor(),
        risk_detector=RiskDetector(),
        sis_connector=LocalSISConnector(data_dir=settings.local_data_dir),
        checkpoint_store=LocalCheckpointStore(data_dir=settings.local_data_dir),
        catalog=LocalJobCatalog(staging_dir=settings.gcs_local_staging_dir),
        review_store=review_store,
        verify_max_iterations=DEFAULT_VERIFY_MAX_ITERATIONS,
        sis_breaker=breaker,
    )


def sis_events(settings) -> list[dict]:
    path = settings.local_data_dir / "sis_writes.jsonl"
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


async def test_blast_radius_contains_exploding_submission(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    memory_manager = MemoryManager.from_settings(settings)
    primary = ExplodingEvaluator(
        {student: 0.95 for student in STUDENTS}, explode_for={"stu-002"}
    )
    runner = build_harness_runner(settings, memory_manager, primary)
    stage_batch(settings, "job-blast")
    record = await runner.process(make_event("job-blast"))

    assert record.stage == JobStage.COMPLETED
    assert written_students(settings) == {"stu-001", "stu-003"}
    report = await verification_report(settings, "job-blast")
    assert report.passed is False
    failed_check = next(
        check for check in report.checks if check.name == "submissions_graded"
    )
    assert failed_check.passed is False
    assert failed_check.detail == "2/3 graded"


async def test_batch_anomaly_breaker_suspends_whole_batch(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    memory_manager = MemoryManager.from_settings(settings)
    confidences = {student: 0.95 for student in STUDENTS}
    confidences["stu-001"] = 0.6
    confidences["stu-002"] = 0.6
    runner = build_harness_runner(
        settings,
        memory_manager,
        ConfidenceMapEvaluator(confidences),
        breaker=BatchAnomalyBreaker(threshold=0.15),
    )
    stage_batch(settings, "job-breaker")
    record = await runner.process(make_event("job-breaker"))

    assert record.stage == JobStage.COMPLETED
    assert written_students(settings) == set()
    review_store = LocalReviewStore(data_dir=settings.local_data_dir)
    pending = await review_store.list_pending()
    assert len(pending) == 3
    breaker_items = [
        item for item in pending if "batch anomaly breaker" in item.reasons[0]
    ]
    assert len(breaker_items) == 1
    assert {item.student_id for item in pending} == set(STUDENTS)


def test_synced_records_carry_provenance_ledger(tmp_path: Path) -> None:
    import asyncio

    settings = make_settings(tmp_path)
    memory_manager = MemoryManager.from_settings(settings)
    primary = ConfidenceMapEvaluator({student: 0.95 for student in STUDENTS})

    async def run() -> None:
        runner = build_harness_runner(settings, memory_manager, primary)
        stage_batch(settings, "job-prov")
        record = await runner.process(make_event("job-prov"))
        assert record.stage == JobStage.COMPLETED

    asyncio.run(run())
    events = sis_events(settings)
    assert events
    for event in events:
        for record in event["request"]["records"]:
            provenance = record["provenance"]
            assert provenance is not None
            assert len(provenance["prompt_version_sha"]) == 64
            assert provenance["evidence_hashes"]
            assert all(len(h) == 64 for h in provenance["evidence_hashes"])


async def test_hallucinated_quote_lands_in_quarantine_via_faithfulness(
    tmp_path: Path,
) -> None:
    settings = make_settings(tmp_path)
    memory_manager = MemoryManager.from_settings(settings)
    stage_batch(settings, "job-faith")
    root = settings.gcs_local_staging_dir / BUCKET / PREFIX
    (root / "stu-001.txt").write_text(
        "completely unrelated transcript", encoding="utf-8"
    )
    primary = ConfidenceMapEvaluator({student: 0.95 for student in STUDENTS})
    runner = build_harness_runner(settings, memory_manager, primary)
    record = await runner.process(make_event("job-faith"))

    assert record.stage == JobStage.COMPLETED
    assert "stu-001" not in written_students(settings)
    assert "stu-003" in written_students(settings)
    review_store = LocalReviewStore(data_dir=settings.local_data_dir)
    item = await review_store.get("job-faith:stu-001")
    assert item is not None
    assert any("confidence 0.000" in reason for reason in item.reasons)
