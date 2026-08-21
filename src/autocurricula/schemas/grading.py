from pydantic import Field, field_validator

from autocurricula.schemas.common import FrozenStrictModel, JobId, TzAwareDatetime


class EvidenceSpan(FrozenStrictModel):
    page: int = Field(ge=1)
    quote: str = Field(min_length=1)
    rationale: str = Field(min_length=1)


class CriterionScore(FrozenStrictModel):
    criterion_id: str = Field(min_length=1)
    score: float = Field(ge=0)
    comment: str = Field(min_length=1)
    evidence: list[EvidenceSpan] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)


class GradingResult(FrozenStrictModel):
    submission_id: str = Field(min_length=1)
    criterion_scores: list[CriterionScore] = Field(min_length=1)
    total_score: float = Field(ge=0)
    percentage: float = Field(ge=0, le=100)
    feedback: str = Field(min_length=1)

    @field_validator("criterion_scores")
    @classmethod
    def _unique_criterion_ids(cls, value: list[CriterionScore]) -> list[CriterionScore]:
        ids = [item.criterion_id for item in value]
        if len(ids) != len(set(ids)):
            raise ValueError("criterion_id values must be unique within a grading result")
        return value


class GradingBatchResult(FrozenStrictModel):
    job_id: JobId
    results: list[GradingResult] = Field(default_factory=list)
    graded_at: TzAwareDatetime
    model_id: str = Field(min_length=1)

    @field_validator("results")
    @classmethod
    def _unique_submission_ids(cls, value: list[GradingResult]) -> list[GradingResult]:
        ids = [item.submission_id for item in value]
        if len(ids) != len(set(ids)):
            raise ValueError("submission_id values must be unique within a batch result")
        return value
