from enum import Enum
from typing import Union

from pydantic import Field

from autocurricula.schemas.common import FrozenStrictModel

ATTR_GEN_AI_SYSTEM = "gen_ai.system"
ATTR_GEN_AI_USAGE_TOKENS = "gen_ai.usage.tokens"
ATTR_AGENT_STAGE = "agent.stage"
ATTR_EVIDENCE_SPAN_MATCH = "evidence.span_match"

SpanAttributeValue = Union[str, bool, int, float]


class SpanStatus(str, Enum):
    OK = "ok"
    ERROR = "error"


class TypedSpan(FrozenStrictModel):
    name: str = Field(min_length=1)
    trace_id: str = Field(min_length=8)
    span_id: str = Field(min_length=1)
    parent_id: str | None = None
    stage: str | None = None
    status: SpanStatus = SpanStatus.OK
    duration_ms: float = Field(ge=0.0)
    attributes: dict[str, SpanAttributeValue] = Field(default_factory=dict)
