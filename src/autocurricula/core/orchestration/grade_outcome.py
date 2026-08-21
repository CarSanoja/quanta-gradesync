from dataclasses import dataclass
from typing import Any

from autocurricula.schemas.grading import GradingResult
from autocurricula.schemas.verification import GradeStageReport, SubmissionFailure

GRADE_REPORT_KEY = "grade_report"
FAILURE_REASON = "this exam could not be graded automatically"


def grading_failure_reason(detail: str) -> str:
    return f"{FAILURE_REASON}: {detail}"


@dataclass(frozen=True)
class GradeOutcome:
    submission_id: str
    student_id: str
    result: GradingResult | None = None
    failure: SubmissionFailure | None = None

    @property
    def failed(self) -> bool:
        return self.failure is not None


def build_failure(submission, detail: str) -> SubmissionFailure:
    return SubmissionFailure(
        submission_id=submission.submission_id,
        student_id=submission.student_id,
        reason=grading_failure_reason(detail),
    )


def store_grade_report(
    session: Any,
    job_id: str,
    manifest_submissions: int,
    failures: list[SubmissionFailure],
    faithfulness: dict[str, str],
) -> GradeStageReport:
    report = GradeStageReport(
        job_id=job_id,
        manifest_submissions=manifest_submissions,
        failures=list(failures),
        faithfulness=dict(faithfulness),
    )
    session.set_stage_result(GRADE_REPORT_KEY, report)
    return report


def load_grade_report(session: Any) -> GradeStageReport | None:
    try:
        return session.get_stage_result(GRADE_REPORT_KEY, GradeStageReport)
    except Exception:
        return None
