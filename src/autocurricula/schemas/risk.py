from enum import StrEnum

from pydantic import Field

from autocurricula.schemas.common import FrozenStrictModel, JobId, StudentId, TzAwareDatetime


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RiskDriver(FrozenStrictModel):
    metric: str = Field(min_length=1)
    value: float
    threshold: float
    explanation: str = Field(min_length=1)


class RiskAssessment(FrozenStrictModel):
    student_id: StudentId
    job_id: JobId
    risk_score: float = Field(ge=0, le=1)
    level: RiskLevel
    drivers: list[RiskDriver] = Field(default_factory=list)
    recommended_interventions: list[str] = Field(default_factory=list)
    assessed_at: TzAwareDatetime
