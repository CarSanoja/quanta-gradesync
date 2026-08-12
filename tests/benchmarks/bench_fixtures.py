import asyncio
from datetime import datetime, timezone

from autocurricula.agents.risk_detector import RiskDetector
from autocurricula.config.settings import Settings
from autocurricula.core.memory.manager import MemoryManager
from autocurricula.core.orchestration.catalog import (
    MANIFEST_NAME,
    BatchManifest,
    LocalJobCatalog,
)
from autocurricula.core.orchestration.job_state import LocalCheckpointStore
from autocurricula.core.orchestration.runner import JobRunner
from autocurricula.core.review import LocalReviewStore
from autocurricula.schemas.curriculum import (
    Competency,
    CurriculumAuditResult,
    CurriculumStandard,
)
from autocurricula.schemas.events import PubSubJobEvent
from autocurricula.schemas.exam import ExamBatch, ExamFile, ExamSubmission
from autocurricula.schemas.grading import CriterionScore, EvidenceSpan, GradingResult
from autocurricula.schemas.rubric import MasteryLevel, Rubric, RubricCriterion
from autocurricula.tools.gcs_fetcher import LocalStagingFetcher
from autocurricula.tools.sis_connector import LocalSISConnector

BENCH_BUCKET = "bench-exams"
SUBJECT = "mathematics"
GRADE_LEVEL = "grade-8"
COMPETENCY_CODES = ("M.8.2.1", "M.8.4.2")
CRITERIA = (("crit-a", 4.0), ("crit-b", 6.0))
SEATS = (1, 2)
SCRIPTED_MODEL = "scripted-benchmark-evaluator"
STAGED_FILE_BODY = b"benchmark-staged-bytes"
TRIGGERED_AT = datetime(2026, 5, 12, 8, 30, tzinfo=timezone.utc)


def bench_id(prefix: str, index: int, suffix: str = "") -> str:
    return f"{prefix}-{index:04d}{suffix}"


def bench_prefix(index: int) -> str:
    return f"batches/{bench_id('job', index)}"


def scripted_ratio(criterion_id: str) -> float:
    return 0.75 if criterion_id.endswith("a") else 0.5


def build_standard() -> CurriculumStandard:
    return CurriculumStandard(
        country="bench-land",
        version="2026.1",
        competencies=[
            Competency(
                code=code,
                description=f"{code} benchmark competency",
                grade_level=GRADE_LEVEL,
                subject=SUBJECT,
            )
            for code in COMPETENCY_CODES
        ],
    )


def build_rubric(index: int) -> Rubric:
    marker = f"marker{index:04d}"
    return Rubric(
        rubric_id=bench_id("rub", index),
        subject=SUBJECT,
        version=1,
        criteria=[
            RubricCriterion(
                criterion_id=criterion_id,
                description=f"{criterion_id} benchmark reasoning {marker}",
                weight=1.0,
                max_score=max_score,
                mastery_descriptions={level: f"{level.value} {marker}" for level in MasteryLevel},
            )
            for criterion_id, max_score in CRITERIA
        ],
    )


def build_submission(index: int, seat: int) -> ExamSubmission:
    submission_id = bench_id("sub", index, f"-{seat:03d}")
    uri = f"gs://{BENCH_BUCKET}/{bench_prefix(index)}/{submission_id}.jpg"
    return ExamSubmission(
        submission_id=submission_id,
        student_id=bench_id("stu", index, f"-{seat:03d}"),
        files=[ExamFile(gcs_uri=uri, mime_type="image/jpeg", page_count=1)],
    )


def build_batch(index: int) -> ExamBatch:
    return ExamBatch(
        job_id=bench_id("bench-job", index),
        class_id=bench_id("cls", index),
        subject=SUBJECT,
        grade_level=GRADE_LEVEL,
        rubric_id=bench_id("rub", index),
        submissions=[build_submission(index, seat) for seat in SEATS],
    )


def build_event(index: int) -> PubSubJobEvent:
    return PubSubJobEvent(
        job_id=bench_id("bench-job", index),
        bucket=BENCH_BUCKET,
        exam_batch_prefix=bench_prefix(index),
        class_id=bench_id("cls", index),
        subject=SUBJECT,
        triggered_at=TRIGGERED_AT,
    )


def stage_bench_batch(settings: Settings, index: int) -> None:
    root = settings.gcs_local_staging_dir / BENCH_BUCKET / bench_prefix(index)
    manifest = BatchManifest(
        batch=build_batch(index),
        rubric=build_rubric(index),
        curriculum_standard=build_standard(),
    )
    root.mkdir(parents=True, exist_ok=True)
    (root / MANIFEST_NAME).write_text(manifest.model_dump_json(), "utf-8")
    for submission in build_batch(index).submissions:
        (root / f"{submission.submission_id}.jpg").write_bytes(STAGED_FILE_BODY)


class ScriptedGradingEvaluator:
    async def grade(self, submission, rubric, context) -> GradingResult:
        await asyncio.sleep(0)
        scores = [
            CriterionScore(
                criterion_id=item.criterion_id,
                score=item.max_score * scripted_ratio(item.criterion_id),
                comment=f"scripted score for {item.criterion_id}",
                evidence=[
                    EvidenceSpan(
                        page=1,
                        quote=f"scripted evidence for {item.criterion_id}",
                        rationale=f"scripted rationale for {item.criterion_id}",
                    )
                ],
                confidence=0.95,
            )
            for item in rubric.criteria
        ]
        total = sum(score.score for score in scores)
        ceiling = sum(item.max_score for item in rubric.criteria)
        return GradingResult(
            submission_id=submission.submission_id,
            criterion_scores=scores,
            total_score=total,
            percentage=100.0 * total / ceiling,
            feedback=f"scripted feedback for {submission.submission_id}",
        )


class ScriptedAuditor:
    async def audit(self, result, standard, context) -> CurriculumAuditResult:
        await asyncio.sleep(0)
        codes = sorted(item.code for item in standard.competencies)
        return CurriculumAuditResult(
            submission_id=result.submission_id,
            mappings={item.criterion_id: codes for item in result.criterion_scores},
            covered_codes=codes,
            missing_codes=[],
            notes="scripted benchmark audit",
        )


def build_bench_runner(settings: Settings, memory_manager: MemoryManager) -> JobRunner:
    return JobRunner(
        memory_manager=memory_manager,
        fetcher=LocalStagingFetcher(staging_dir=settings.gcs_local_staging_dir),
        grading_evaluator=ScriptedGradingEvaluator(),
        auditor=ScriptedAuditor(),
        risk_detector=RiskDetector(),
        sis_connector=LocalSISConnector(data_dir=settings.local_data_dir),
        checkpoint_store=LocalCheckpointStore(data_dir=settings.local_data_dir),
        catalog=LocalJobCatalog(staging_dir=settings.gcs_local_staging_dir),
        review_store=LocalReviewStore(data_dir=settings.local_data_dir),
        grading_model_id=SCRIPTED_MODEL,
        confidence_threshold=settings.confidence_threshold,
    )
