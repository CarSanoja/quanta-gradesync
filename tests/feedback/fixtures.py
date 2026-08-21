from datetime import UTC, datetime

from autocurricula.schemas.curriculum import CurriculumAuditResult
from autocurricula.schemas.exam import ExamBatch, ExamFile, ExamSubmission
from autocurricula.schemas.feedback import (
    EvidenceSpan,
    FeedbackBand,
    FeedbackPoint,
    StudentFeedback,
)
from autocurricula.schemas.grading import CriterionScore, GradingBatchResult, GradingResult
from autocurricula.schemas.memory import RetrievedContext
from autocurricula.schemas.rubric import MasteryLevel, Rubric, RubricCriterion

GRADED_AT = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)
CRITERION_ID = "factoring"


def make_rubric() -> Rubric:
    return Rubric(
        rubric_id="mat-10a-parcial1",
        subject="Matematicas",
        version=1,
        criteria=[
            RubricCriterion(
                criterion_id=CRITERION_ID,
                description="Factors a quadratic trinomial and justifies the factor pair",
                weight=1.0,
                max_score=4.0,
                mastery_descriptions={
                    MasteryLevel.NO_EVIDENCE: "No factoring work is present.",
                    MasteryLevel.DEVELOPING: "A factor pair is attempted but wrong.",
                    MasteryLevel.PROFICIENT: "Correct factors with a partial justification.",
                    MasteryLevel.ADVANCED: "Correct factors with a written check.",
                },
            )
        ],
    )


def make_submission(student_id: str = "camila-rios") -> ExamSubmission:
    return ExamSubmission(
        submission_id=student_id,
        student_id=student_id,
        files=[
            ExamFile(
                gcs_uri=f"gs://sample_batch/batches/lot/{student_id}.jpg",
                mime_type="image/jpeg",
                page_count=1,
            )
        ],
    )


def make_batch(grade_level: str = "10", student_id: str = "camila-rios") -> ExamBatch:
    return ExamBatch(
        job_id="job-feedback-1",
        class_id="10A",
        subject="Matematicas",
        grade_level=grade_level,
        rubric_id="mat-10a-parcial1",
        submissions=[make_submission(student_id)],
    )


def make_context() -> RetrievedContext:
    return RetrievedContext(query="factoring quadratics", chunks=[])


def make_student_feedback(
    band: FeedbackBand = FeedbackBand.UPPER_SECONDARY,
) -> StudentFeedback:
    return StudentFeedback(
        band=band,
        headline="Your factor pair is correct and your check is missing.",
        strengths=[
            FeedbackPoint(
                text="You found the pair that multiplies to 6 and adds to 5.",
                evidence=EvidenceSpan(
                    page=1,
                    quote="(x + 2)(x + 3)",
                    rationale="The written pair matches the trinomial.",
                ),
            )
        ],
        growth=[
            FeedbackPoint(
                text="Next time, expand the factors to show they return the original.",
                evidence=None,
            )
        ],
        next_step="Expand your factors and compare the result with the question.",
        teacher_note="factoring sits at proficient; the check is the missing move.",
    )


def make_result(
    submission_id: str = "camila-rios",
    student_feedback: StudentFeedback | None = None,
) -> GradingResult:
    return GradingResult(
        submission_id=submission_id,
        criterion_scores=[
            CriterionScore(
                criterion_id=CRITERION_ID,
                score=3.0,
                comment="Correct factors with a partial justification.",
                evidence=[
                    EvidenceSpan(
                        page=1,
                        quote="(x + 2)(x + 3)",
                        rationale="Factor pair written on the page.",
                    )
                ],
                confidence=0.9,
            )
        ],
        total_score=3.0,
        percentage=75.0,
        feedback="Correct factoring; next step is showing the expansion check.",
        student_feedback=student_feedback,
    )


def make_batch_result(*results: GradingResult) -> GradingBatchResult:
    return GradingBatchResult(
        job_id="job-feedback-1",
        results=list(results),
        graded_at=GRADED_AT,
        model_id="gemini-3.5-flash",
    )


def make_audit(submission_id: str = "camila-rios") -> CurriculumAuditResult:
    return CurriculumAuditResult(
        submission_id=submission_id,
        mappings={CRITERION_ID: ["MAT.10.1"]},
        covered_codes=["MAT.10.1"],
        missing_codes=[],
        notes="factoring evidence supports MAT.10.1",
    )
