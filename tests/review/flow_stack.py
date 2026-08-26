import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

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
from autocurricula.core.review import LocalReviewStore, ReviewService
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

BUCKET = "flow-exams"
PREFIX = "batches/2026_matematicas_10A_Parcial1"
TRIGGERED_AT = datetime(2026, 8, 17, 10, 0, tzinfo=UTC)
STUDENTS = ("stu-001", "stu-002", "stu-003")
LOW_CONFIDENCE_STUDENT = "stu-002"


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        local_mode=True,
        gcp_project_id="",
        local_data_dir=tmp_path / "local_data",
        gcs_local_staging_dir=tmp_path / "staging",
    )


def make_rubric() -> Rubric:
    return Rubric(
        rubric_id="rub-flow-1",
        subject="matematicas",
        version=1,
        criteria=[
            RubricCriterion(
                criterion_id="crit-a",
                description="razonamiento",
                weight=1.0,
                max_score=4.0,
                mastery_descriptions={level: level.value for level in MasteryLevel},
            )
        ],
    )


def make_standard() -> CurriculumStandard:
    return CurriculumStandard(
        country="cl",
        version="2026.1",
        competencies=[
            Competency(
                code="MAT.8.1",
                description="modela",
                grade_level="grade-8",
                subject="matematicas",
            )
        ],
    )


def make_event(job_id: str) -> PubSubJobEvent:
    return PubSubJobEvent(
        job_id=job_id,
        bucket=BUCKET,
        exam_batch_prefix=PREFIX,
        class_id="10A",
        subject="matematicas",
        triggered_at=TRIGGERED_AT,
    )


def stage_batch(settings: Settings, job_id: str) -> None:
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
            for student in STUDENTS
        ],
    )
    manifest = BatchManifest(
        batch=batch, rubric=make_rubric(), curriculum_standard=make_standard()
    )
    root = settings.gcs_local_staging_dir / BUCKET / PREFIX
    root.mkdir(parents=True, exist_ok=True)
    (root / MANIFEST_NAME).write_text(manifest.model_dump_json(), encoding="utf-8")
    for student in STUDENTS:
        (root / f"{student}.jpg").write_bytes(b"scan")


class MixedConfidenceEvaluator:
    async def grade(self, submission, rubric, context) -> GradingResult:
        await asyncio.sleep(0)
        confidence = 0.6 if submission.student_id == LOW_CONFIDENCE_STUDENT else 0.95
        criterion = rubric.criteria[0]
        score = criterion.max_score * (0.5 if confidence < 0.85 else 0.9)
        return GradingResult(
            submission_id=submission.submission_id,
            criterion_scores=[
                CriterionScore(
                    criterion_id=criterion.criterion_id,
                    score=score,
                    comment="assessed with cited page",
                    evidence=[
                        EvidenceSpan(
                            page=1,
                            quote=f"visible answer of {submission.student_id}",
                            rationale="matches rubric criterion",
                        )
                    ],
                    confidence=confidence,
                )
            ],
            total_score=score,
            percentage=100.0 * score / criterion.max_score,
            feedback=f"feedback for {submission.student_id}",
        )


class ScriptedAuditor:
    async def audit(self, result, standard, context) -> CurriculumAuditResult:
        await asyncio.sleep(0)
        codes = [item.code for item in standard.competencies]
        return CurriculumAuditResult(
            submission_id=result.submission_id,
            mappings={result.criterion_scores[0].criterion_id: codes},
            covered_codes=codes,
            missing_codes=[],
            notes="scripted",
        )


def build_stack(
    settings: Settings, memory_manager: MemoryManager
) -> tuple[JobRunner, LocalReviewStore, ReviewService]:
    review_store = LocalReviewStore(data_dir=settings.local_data_dir)
    service = ReviewService(
        store=review_store,
        sis_connector=LocalSISConnector(data_dir=settings.local_data_dir),
        memory_manager=memory_manager,
    )
    runner = JobRunner(
        memory_manager=memory_manager,
        fetcher=LocalStagingFetcher(staging_dir=settings.gcs_local_staging_dir),
        grading_evaluator=MixedConfidenceEvaluator(),
        auditor=ScriptedAuditor(),
        risk_detector=RiskDetector(),
        sis_connector=LocalSISConnector(data_dir=settings.local_data_dir),
        checkpoint_store=LocalCheckpointStore(data_dir=settings.local_data_dir),
        catalog=LocalJobCatalog(staging_dir=settings.gcs_local_staging_dir),
        review_store=review_store,
    )
    return runner, review_store, service


def written_students(settings: Settings) -> set[str]:
    path = settings.local_data_dir / "sis_writes.jsonl"
    if not path.is_file():
        return set()
    students: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        for record in event["request"]["records"]:
            students.add(record["student_id"])
    return students
