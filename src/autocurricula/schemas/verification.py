from pydantic import Field

from autocurricula.schemas.common import FrozenStrictModel, JobId, TzAwareDatetime

OUTCOME_RECOVERED = "recovered_pending_approval"
OUTCOME_STILL_QUARANTINED = "still_quarantined"


class GoalCheck(FrozenStrictModel):
    name: str = Field(min_length=1)
    passed: bool
    detail: str = ""


class ReworkAttempt(FrozenStrictModel):
    iteration: int = Field(ge=1)
    outcomes: dict[str, str] = Field(min_length=1)


class SubmissionFailure(FrozenStrictModel):
    submission_id: str = Field(min_length=1)
    student_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class GradeStageReport(FrozenStrictModel):
    job_id: JobId
    manifest_submissions: int = Field(default=0, ge=0)
    failures: list[SubmissionFailure] = Field(default_factory=list)
    faithfulness: dict[str, str] = Field(default_factory=dict)

    def failed_students(self) -> set[str]:
        return {failure.student_id for failure in self.failures}


class MissingFilesReport(FrozenStrictModel):
    checked: bool = False
    manifest_count: int = Field(default=0, ge=0)
    listed_count: int = Field(default=0, ge=0)
    missing: list[str] = Field(default_factory=list)
    detail: str = ""


class VerificationReport(FrozenStrictModel):
    job_id: JobId
    passed: bool
    checks: list[GoalCheck] = Field(min_length=1)
    rework_attempts: list[ReworkAttempt] = Field(default_factory=list)
    pending_human_approval: list[str] = Field(default_factory=list)
    unresolved_submission_ids: list[str] = Field(default_factory=list)
    failed_submission_ids: list[str] = Field(default_factory=list)
    missing_files: MissingFilesReport | None = None
    verified_at: TzAwareDatetime
