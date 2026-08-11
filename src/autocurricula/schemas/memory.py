from typing import Annotated

from pydantic import Field, field_validator

from autocurricula.schemas.common import ClassId, FrozenStrictModel, StudentId, TzAwareDatetime


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
