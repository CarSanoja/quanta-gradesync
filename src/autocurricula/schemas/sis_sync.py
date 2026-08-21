from typing import Self

from pydantic import Field, field_validator, model_validator

from autocurricula.schemas.common import FrozenStrictModel, JobId, StudentId, TzAwareDatetime
from autocurricula.schemas.feedback import StudentFeedback
from autocurricula.schemas.provenance import Provenance


class SISGradeRecord(FrozenStrictModel):
    student_id: StudentId
    subject: str = Field(min_length=1)
    score: float = Field(ge=0)
    percentage: float = Field(ge=0, le=100)
    feedback: str = Field(min_length=1)
    student_feedback: StudentFeedback | None = None
    competency_codes: list[str] = Field(default_factory=list)
    provenance: Provenance | None = None
    graded_at: TzAwareDatetime


class SISWriteRequest(FrozenStrictModel):
    job_id: JobId
    records: list[SISGradeRecord] = Field(default_factory=list)

    @field_validator("records")
    @classmethod
    def _unique_students(cls, value: list[SISGradeRecord]) -> list[SISGradeRecord]:
        ids = [record.student_id for record in value]
        if len(ids) != len(set(ids)):
            raise ValueError("student_id values must be unique within a write request")
        return value


class SISWriteResult(FrozenStrictModel):
    job_id: JobId
    per_record_statuses: dict[StudentId, str] = Field(default_factory=dict)
    succeeded_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    quarantined_count: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _counts_match_statuses(self) -> Self:
        if self.succeeded_count + self.failed_count != len(self.per_record_statuses):
            raise ValueError(
                "succeeded_count plus failed_count must equal per_record_statuses size"
            )
        return self
