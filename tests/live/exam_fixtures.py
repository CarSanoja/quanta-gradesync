from pathlib import Path

from autocurricula.schemas.curriculum import Competency, CurriculumStandard
from autocurricula.schemas.exam import ExamFile, ExamSubmission
from autocurricula.schemas.memory import RetrievedChunk, RetrievedContext
from autocurricula.schemas.rubric import MasteryLevel, Rubric, RubricCriterion

SUBMISSION_ID = "live-sub-001"
CRITERION_ID = "alg-factor-1"
MAX_SCORE = 10.0


def build_rubric() -> Rubric:
    criterion = RubricCriterion(
        criterion_id=CRITERION_ID,
        description="Factors a quadratic trinomial into two correct binomials",
        weight=1.0,
        max_score=MAX_SCORE,
        mastery_descriptions={
            MasteryLevel.NO_EVIDENCE: "No factoring work is visible.",
            MasteryLevel.DEVELOPING: "Factoring is attempted but the binomials are wrong.",
            MasteryLevel.PROFICIENT: "The trinomial is factored into two correct binomials.",
            MasteryLevel.ADVANCED: "Correct factoring plus a verification of the product.",
        },
    )
    return Rubric(
        rubric_id="live-rubric-algebra-1",
        subject="algebra",
        version=1,
        criteria=[criterion],
    )


def build_submission(image_path: Path) -> ExamSubmission:
    file = ExamFile(
        gcs_uri="gs://live-exam-fixtures/live-sub-001/page-1.jpg",
        local_path=str(image_path),
        mime_type="image/jpeg",
        page_count=1,
    )
    return ExamSubmission(
        submission_id=SUBMISSION_ID,
        student_id="live-student-001",
        files=[file],
    )


def build_context() -> RetrievedContext:
    chunk = RetrievedChunk(
        text="Factoring x^2 + bx + c requires two integers whose product is c and sum is b.",
        source="live-fixture://algebra-notes",
        score=0.9,
    )
    return RetrievedContext(query="factoring quadratic trinomials", chunks=[chunk])


def build_audit_context() -> RetrievedContext:
    chunks = [
        RetrievedChunk(
            text=(
                "Ministry guideline: competency A-SSE.2 is demonstrated when a student "
                "rewrites a quadratic trinomial such as x^2 + x - 6 in factored form."
            ),
            source="live-fixture://ministry-framework.pdf",
            score=0.95,
        ),
        RetrievedChunk(
            text=(
                "Ministry guideline: competency A-APR.1 is demonstrated when a student "
                "multiplies binomials and verifies the resulting product."
            ),
            source="live-fixture://ministry-framework.pdf",
            score=0.9,
        ),
    ]
    return RetrievedContext(query="factoring competencies coverage", chunks=chunks)


def build_standard() -> CurriculumStandard:
    return CurriculumStandard(
        country="US",
        version="live-fixture-1",
        competencies=[
            Competency(
                code="A-SSE.2",
                description="Use the structure of an expression to rewrite it in factored form",
                grade_level="8",
                subject="algebra",
            ),
            Competency(
                code="A-APR.1",
                description="Multiply polynomials and verify products",
                grade_level="8",
                subject="algebra",
            ),
        ],
    )
