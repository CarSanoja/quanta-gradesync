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


class VerificationReport(FrozenStrictModel):
    job_id: JobId
    passed: bool
    checks: list[GoalCheck] = Field(min_length=1)
    rework_attempts: list[ReworkAttempt] = Field(default_factory=list)
    pending_human_approval: list[str] = Field(default_factory=list)
    unresolved_submission_ids: list[str] = Field(default_factory=list)
    verified_at: TzAwareDatetime
