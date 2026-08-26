from enum import Enum
from typing import Union

from pydantic import Field

from autocurricula.schemas.common import FrozenStrictModel

LIVE_SUBCOLLECTION = "live"

LiveAttributeValue = Union[str, bool, int, float]


class LiveEventKind(str, Enum):
    SPAN_START = "span_start"
    SPAN_END = "span_end"
    LLM_CALL = "llm_call"


class LiveEventStatus(str, Enum):
    RUNNING = "running"
    OK = "ok"
    ERROR = "error"


class LlmExchange(FrozenStrictModel):
    model: str = ""
    request_excerpt: str = ""
    response_excerpt: str = ""
    finish_reason: str = ""
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    truncated: bool = False


class LiveEvent(FrozenStrictModel):
    seq: int = Field(ge=1)
    recorded_at: str = Field(min_length=1)
    job_id: str = Field(min_length=1)
    trace_id: str = Field(min_length=1)
    kind: LiveEventKind
    name: str = Field(min_length=1)
    status: LiveEventStatus = LiveEventStatus.OK
    stage: str | None = None
    agent_id: str | None = None
    principal: str | None = None
    student_id: str | None = None
    span_id: str | None = None
    parent_span_id: str | None = None
    duration_ms: float | None = Field(default=None, ge=0.0)
    attributes: dict[str, LiveAttributeValue] = Field(default_factory=dict)
    llm: LlmExchange | None = None


def event_document_id(seq: int) -> str:
    return f"{seq:06d}"
