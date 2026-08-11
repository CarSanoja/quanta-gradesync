from enum import StrEnum
from typing import Any, TypeVar

from pydantic import Field, TypeAdapter

from autocurricula.schemas.common import JobId, StrictBaseModel
from autocurricula.schemas.exam import ExamBatch


class StageStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class SessionState(StrictBaseModel):
    job_id: JobId
    batch: ExamBatch | None = None
    stage_results: dict[str, Any] = Field(default_factory=dict)
    stage_statuses: dict[str, str] = Field(default_factory=dict)


T = TypeVar("T")


class SessionMemory:
    def __init__(self, job_id: JobId, batch: ExamBatch | None = None) -> None:
        self._state = SessionState(job_id=job_id, batch=batch)

    @property
    def state(self) -> SessionState:
        return self._state

    @property
    def job_id(self) -> str:
        return self._state.job_id

    @property
    def batch(self) -> ExamBatch | None:
        return self._state.batch

    def mark_stage(self, stage: str, status: StageStatus) -> None:
        if not stage:
            raise ValueError("stage name must not be empty")
        self._state.stage_statuses[stage] = status.value

    def stage_status(self, stage: str) -> StageStatus | None:
        value = self._state.stage_statuses.get(stage)
        return StageStatus(value) if value is not None else None

    def set_stage_result(self, stage: str, result: Any) -> None:
        if not stage:
            raise ValueError("stage name must not be empty")
        self._state.stage_results[stage] = result

    def get_stage_result(self, stage: str, result_type: type[T]) -> T | None:
        if stage not in self._state.stage_results:
            return None
        raw = self._state.stage_results[stage]
        if isinstance(result_type, type) and isinstance(raw, result_type):
            return raw
        return TypeAdapter(result_type).validate_python(raw)

    def has_stage_result(self, stage: str) -> bool:
        return stage in self._state.stage_results

    def snapshot(self) -> SessionState:
        return self._state.model_copy(deep=True)
