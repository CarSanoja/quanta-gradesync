from enum import Enum

from pydantic import Field

from autocurricula.schemas.common import FrozenStrictModel, JobId, StudentId, TzAwareDatetime
from autocurricula.schemas.grading import EvidenceSpan
from autocurricula.schemas.sis_sync import SISGradeRecord

REQUIRES_HUMAN_REVIEW = "requires_human_review"


class ReviewStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DISMISSED = "dismissed"
    RESOLVED = "resolved"


class ReviewKind(str, Enum):
    GRADE = "grade"
    FAILED_GRADING = "failed_grading"
    MISSING_FILE = "missing_file"


def build_review_id(job_id: str, student_id: str) -> str:
    return f"{job_id}:{student_id}"


class ReviewItem(FrozenStrictModel):
    review_id: str = Field(min_length=3)
    job_id: JobId
    student_id: StudentId
    subject: str = Field(min_length=1)
    kind: ReviewKind = ReviewKind.GRADE
    reasons: list[str] = Field(min_length=1)
    evidence: list[EvidenceSpan] = Field(default_factory=list)
    document_paths: list[str] = Field(default_factory=list)
    proposed_record: SISGradeRecord
    status: ReviewStatus = ReviewStatus.PENDING
    rework_notes: list[str] = Field(default_factory=list)
    created_at: TzAwareDatetime
    decided_at: TzAwareDatetime | None = None
