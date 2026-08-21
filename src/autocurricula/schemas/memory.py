from enum import Enum
from typing import Annotated

from pydantic import Field, field_validator

from autocurricula.schemas.common import (
    ClassId,
    FrozenStrictModel,
    JobId,
    StudentId,
    TzAwareDatetime,
)

FACT_KEY_SEPARATOR = "::"


class RetrievedChunk(FrozenStrictModel):
    text: str = Field(min_length=1)
    source: str = Field(min_length=1)
    score: float = Field(ge=0, le=1)


class RetrievedContext(FrozenStrictModel):
    query: str = Field(min_length=1)
    chunks: list[RetrievedChunk] = Field(default_factory=list)


class TermSnapshot(FrozenStrictModel):
    term: str = Field(min_length=1)
    avg_percentage: float = Field(ge=0, le=100)
    submissions_count: int = Field(ge=0)
    risk_history: list[Annotated[float, Field(ge=0, le=1)]] = Field(default_factory=list)


class FactSource(str, Enum):
    BATCH_SYNC = "batch_sync"
    HUMAN_APPROVAL = "human_approval"
    HUMAN_OVERRIDE = "human_override"


class AssessmentFact(FrozenStrictModel):
    fact_id: str = Field(min_length=1)
    student_id: StudentId
    job_id: JobId
    term: str = Field(min_length=1)
    avg_percentage: float = Field(ge=0, le=100)
    submissions_count: int = Field(ge=1)
    source: FactSource
    recorded_at: TzAwareDatetime


def assessment_fact_id(job_id: str, student_id: str) -> str:
    return f"{job_id}{FACT_KEY_SEPARATOR}{student_id}"


class EpisodicStudentProfile(FrozenStrictModel):
    student_id: StudentId
    terms: list[TermSnapshot] = Field(default_factory=list)

    @field_validator("terms")
    @classmethod
    def _unique_terms(cls, value: list[TermSnapshot]) -> list[TermSnapshot]:
        terms = [snapshot.term for snapshot in value]
        if len(terms) != len(set(terms)):
            raise ValueError("term values must be unique within a student profile")
        return value


class ClassCompetencySnapshot(FrozenStrictModel):
    class_id: ClassId
    subject: str = Field(min_length=1)
    competency_code: str = Field(min_length=1)
    avg_mastery: float = Field(ge=0, le=1)
    student_count: int = Field(ge=0)
    updated_at: TzAwareDatetime
