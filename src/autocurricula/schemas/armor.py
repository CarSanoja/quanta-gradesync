from enum import StrEnum

from pydantic import Field

from autocurricula.schemas.common import FrozenStrictModel, JobId


class ArmorSeverity(StrEnum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ArmorVerdict(FrozenStrictModel):
    injection_detected: bool
    quoted_text: str = ""
    severity: ArmorSeverity = ArmorSeverity.NONE
    rationale: str = ""


class ArmorBatchReport(FrozenStrictModel):
    job_id: JobId
    verdicts: dict[str, ArmorVerdict] = Field(default_factory=dict)

    def verdict_for(self, submission_id: str) -> ArmorVerdict | None:
        return self.verdicts.get(submission_id)
