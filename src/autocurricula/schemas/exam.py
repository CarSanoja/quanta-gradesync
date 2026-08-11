from pydantic import Field, field_validator

from autocurricula.schemas.common import (
    ClassId,
    FrozenStrictModel,
    JobId,
    StrictBaseModel,
    StudentId,
)


class ExamFile(StrictBaseModel):
    gcs_uri: str = Field(min_length=1, pattern=r"^gs://\S+")
    local_path: str | None = None
    mime_type: str = Field(min_length=1, pattern=r"^\S+/\S+$")
    page_count: int = Field(ge=1)


class ExamSubmission(StrictBaseModel):
    submission_id: str = Field(min_length=1)
    student_id: StudentId
    files: list[ExamFile] = Field(min_length=1)


class ExamBatch(FrozenStrictModel):
    job_id: JobId
    class_id: ClassId
    subject: str = Field(min_length=1)
    grade_level: str = Field(min_length=1)
    rubric_id: str = Field(min_length=1)
    submissions: list[ExamSubmission] = Field(min_length=1)

    @field_validator("submissions")
    @classmethod
    def _unique_submission_ids(cls, value: list[ExamSubmission]) -> list[ExamSubmission]:
        ids = [submission.submission_id for submission in value]
        if len(ids) != len(set(ids)):
            raise ValueError("submission_id values must be unique within a batch")
        return value
