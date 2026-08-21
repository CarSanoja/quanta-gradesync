from datetime import datetime, timezone

from autocurricula.core.memory.manager import MemoryManager
from autocurricula.schemas.exam import ExamBatch, ExamFile, ExamSubmission
from autocurricula.schemas.grading import (
    CriterionScore,
    GradingBatchResult,
    GradingResult,
)
from autocurricula.schemas.memory import TermSnapshot

GRADED_AT = datetime(2026, 8, 3, 9, 0, tzinfo=timezone.utc)
TERM = "term-2026-08"
STUDENT = "stu-001"
MAX_SCORE = 4.0


def make_batch(job_id: str, students: list[str]) -> ExamBatch:
    return ExamBatch(
        job_id=job_id,
        class_id="10A",
        subject="matematicas",
        grade_level="grade-8",
        rubric_id="rub-1",
        submissions=[
            ExamSubmission(
                submission_id=f"{job_id}-{student}",
                student_id=student,
                files=[
                    ExamFile(
                        gcs_uri=f"gs://exams/{job_id}/{student}.jpg",
                        mime_type="image/jpeg",
                        page_count=1,
                    )
                ],
            )
            for student in students
        ],
    )


def make_result(job_id: str, percentages: dict[str, float]) -> GradingBatchResult:
    return GradingBatchResult(
        job_id=job_id,
        graded_at=GRADED_AT,
        model_id="gemini-3.5-flash",
        results=[
            GradingResult(
                submission_id=f"{job_id}-{student}",
                criterion_scores=[
                    CriterionScore(
                        criterion_id="crit-a",
                        score=MAX_SCORE * percentage / 100.0,
                        comment="assessed against the rubric",
                        confidence=0.95,
                    )
                ],
                total_score=MAX_SCORE * percentage / 100.0,
                percentage=percentage,
                feedback=f"feedback for {student}",
            )
            for student, percentage in percentages.items()
        ],
    )


async def persist(manager: MemoryManager, job_id: str, percentage: float) -> None:
    await manager.persist_outcomes(
        make_batch(job_id, [STUDENT]),
        make_result(job_id, {STUDENT: percentage}),
        TERM,
    )


async def snapshot(manager: MemoryManager) -> TermSnapshot:
    profile = await manager.persistent_store.get_profile(STUDENT)
    assert profile is not None
    assert [term.term for term in profile.terms] == [TERM]
    return profile.terms[0]
