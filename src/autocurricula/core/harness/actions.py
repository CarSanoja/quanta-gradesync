from enum import Enum
from typing import Any

from pydantic import Field

from autocurricula.schemas.common import StrictBaseModel


class ActionRisk(str, Enum):
    PASSIVE = "passive"
    INTERNAL_MUTATION = "internal_mutation"
    EXTERNAL_MUTATION = "external_mutation"


class PermissionDecision(str, Enum):
    ALLOW = "allow"
    QUARANTINE = "quarantine"
    DENY = "deny"


class ToolAction(StrictBaseModel):
    tool: str = Field(min_length=1)
    target: str = Field(min_length=1)
    risk: ActionRisk
    payload: dict[str, Any] = Field(default_factory=dict)


class PermissionVerdict(StrictBaseModel):
    decision: PermissionDecision
    tool: str
    target: str
    reasons: list[str] = Field(default_factory=list)

    @property
    def allowed(self) -> bool:
        return self.decision == PermissionDecision.ALLOW
