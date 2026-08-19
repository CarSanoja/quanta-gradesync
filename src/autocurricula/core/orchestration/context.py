from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, TypeVar

from pydantic import Field

from autocurricula.core.memory.session_memory import SessionMemory, StageStatus
from autocurricula.core.orchestration.job_state import JobStage
from autocurricula.schemas.common import StrictBaseModel
from autocurricula.schemas.curriculum import CurriculumAuditResult, CurriculumStandard
from autocurricula.schemas.events import PubSubJobEvent
from autocurricula.schemas.exam import ExamBatch
from autocurricula.schemas.grading import GradingBatchResult
from autocurricula.schemas.metrics import OptimizerReport
from autocurricula.schemas.risk import RiskAssessment
from autocurricula.schemas.rubric import Rubric
from autocurricula.schemas.sis_sync import SISWriteResult

STAGE_FETCH = "fetch"
STAGE_GRADE = "grade"
STAGE_AUDIT = "audit"
STAGE_RISK = "risk"
STAGE_SYNC = "sync"
STAGE_VERIFY = "verify"
STAGE_OPTIMIZE = "optimize"

STAGE_COMPLETION: dict[str, JobStage] = {
    STAGE_FETCH: JobStage.FETCHED,
    STAGE_GRADE: JobStage.GRADED,
    STAGE_AUDIT: JobStage.AUDITED,
    STAGE_RISK: JobStage.RISK_ASSESSED,
    STAGE_SYNC: JobStage.SYNCED,
    STAGE_VERIFY: JobStage.VERIFIED,
    STAGE_OPTIMIZE: JobStage.OPTIMIZED,
}

PIPELINE_STAGE_ORDER = tuple(STAGE_COMPLETION)


class FetchOutputs(StrictBaseModel):
    batch: ExamBatch
    rubric: Rubric
    curriculum_standard: CurriculumStandard


class AuditOutputs(StrictBaseModel):
    audits: list[CurriculumAuditResult] = Field(default_factory=list)


class RiskOutputs(StrictBaseModel):
    assessments: list[RiskAssessment] = Field(default_factory=list)


class OptimizeOutputs(StrictBaseModel):
    reports: list[OptimizerReport] = Field(default_factory=list)


class StageExecutionError(RuntimeError):
    def __init__(self, stage: str, message: str) -> None:
        super().__init__(f"stage {stage}: {message}")
        self.stage = stage


T = TypeVar("T")

StageCallable = Callable[["JobContext"], Awaitable["JobContext"]]


@dataclass(frozen=True)
class StageStep:
    name: str
    callable: StageCallable


@dataclass
class JobContext:
    event: PubSubJobEvent
    session: SessionMemory
    recorder: Any = None

    @property
    def job_id(self) -> str:
        return self.session.job_id

    def output(self, stage: str, output_type: type[T]) -> T:
        result = self.session.get_stage_result(stage, output_type)
        if result is None:
            raise StageExecutionError(stage, "stage output is missing")
        return result

    @property
    def fetch_outputs(self) -> FetchOutputs:
        return self.output(STAGE_FETCH, FetchOutputs)

    @property
    def batch(self) -> ExamBatch:
        return self.fetch_outputs.batch

    @property
    def rubric(self) -> Rubric:
        return self.fetch_outputs.rubric

    @property
    def curriculum_standard(self) -> CurriculumStandard:
        return self.fetch_outputs.curriculum_standard

    @property
    def grade_result(self) -> GradingBatchResult:
        return self.output(STAGE_GRADE, GradingBatchResult)

    @property
    def audits(self) -> AuditOutputs:
        return self.output(STAGE_AUDIT, AuditOutputs)

    @property
    def assessments(self) -> RiskOutputs:
        return self.output(STAGE_RISK, RiskOutputs)

    @property
    def sync_result(self) -> SISWriteResult:
        return self.output(STAGE_SYNC, SISWriteResult)

    def complete(self, stage: str, result: Any) -> None:
        self.session.set_stage_result(stage, result)

    def stage_done(self, stage: str) -> bool:
        return (
            self.session.stage_status(stage) == StageStatus.SUCCEEDED
            and self.session.has_stage_result(stage)
        )
