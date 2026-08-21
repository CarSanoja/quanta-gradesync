from enum import Enum

from pydantic import Field

from autocurricula.schemas.common import (
    FrozenStrictModel,
    JobId,
    StudentId,
    TzAwareDatetime,
)


class LabelDecision(str, Enum):
    APPROVE = "approve"
    DISMISS = "dismiss"
    OVERRIDE = "override"


class LabelScore(FrozenStrictModel):
    criterion_id: str = Field(min_length=1)
    machine_score: float | None = Field(default=None, ge=0)
    human_score: float | None = Field(default=None, ge=0)
    max_score: float | None = Field(default=None, gt=0)


class Label(FrozenStrictModel):
    label_id: str = Field(min_length=1)
    review_id: str = Field(min_length=1)
    job_id: JobId
    student_id: StudentId
    subject: str = Field(min_length=1)
    decision: LabelDecision
    scores: list[LabelScore] = Field(default_factory=list)
    machine_percentage: float = Field(ge=0, le=100)
    human_percentage: float | None = Field(default=None, ge=0, le=100)
    prompt_variant_id: str | None = None
    prompt_version_sha: str | None = None
    reviewer_note: str | None = None
    created_at: TzAwareDatetime


def build_label_id(review_id: str, decision: LabelDecision) -> str:
    return f"{review_id}:{decision.value}"
