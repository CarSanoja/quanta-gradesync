from typing import Any

from autocurricula.core.fleet.declarations import (
    GCS_FETCH_BATCH,
    LLM_GENERATE,
    TOOL_CAPABILITIES,
)
from autocurricula.core.fleet.identity import build_grants
from autocurricula.core.harness.actions import ActionRisk, PermissionVerdict, ToolAction
from autocurricula.core.harness.capabilities import (
    AgentAuthorizer,
    CapabilityDenied,
    tool_capability_resolver,
)
from autocurricula.core.harness.permission_gate import PermissionGate
from autocurricula.schemas.telemetry import (
    ATTR_AGENT_CAPABILITY,
    ATTR_AGENT_ID,
    ATTR_AGENT_PRINCIPAL,
    ATTR_PERMISSION_DECISION,
)

DENIAL_SPAN_NAME = "CapabilityDenied"

_authorizer: AgentAuthorizer | None = None


def build_default_authorizer() -> AgentAuthorizer:
    resolver = tool_capability_resolver(
        {tool: capability.value for tool, capability in TOOL_CAPABILITIES.items()}
    )
    return AgentAuthorizer(build_grants(), resolver)


def get_authorizer() -> AgentAuthorizer:
    global _authorizer
    if _authorizer is None:
        _authorizer = build_default_authorizer()
    return _authorizer


def set_authorizer(authorizer: AgentAuthorizer | None) -> None:
    global _authorizer
    _authorizer = authorizer


def reset_authorizer_cache() -> None:
    set_authorizer(None)


def principal_of(agent_id: str) -> str:
    grant = get_authorizer().grant(agent_id)
    return grant.principal_id if grant is not None else "unknown"


def annotate_span(span: Any, agent_id: str) -> None:
    if span is None:
        return
    span.set(ATTR_AGENT_ID, agent_id)
    span.set(ATTR_AGENT_PRINCIPAL, principal_of(agent_id))


def authorize(
    agent_id: str,
    action: ToolAction,
    *,
    gate: PermissionGate | None = None,
    recorder: Any = None,
    parent: Any = None,
) -> PermissionVerdict:
    try:
        return get_authorizer().authorize(agent_id, action, gate=gate)
    except CapabilityDenied as denial:
        _record_denial(recorder, parent, agent_id, denial)
        raise


def authorize_llm(
    agent_id: str,
    target: str,
    *,
    model_id: str = "",
    recorder: Any = None,
    parent: Any = None,
) -> PermissionVerdict:
    action = ToolAction(
        tool=LLM_GENERATE,
        target=target,
        risk=ActionRisk.PASSIVE,
        payload={"model_id": model_id} if model_id else {},
    )
    return authorize(agent_id, action, recorder=recorder, parent=parent)


def authorize_gcs_read(
    agent_id: str, target: str, *, recorder: Any = None, parent: Any = None
) -> PermissionVerdict:
    action = ToolAction(
        tool=GCS_FETCH_BATCH, target=target, risk=ActionRisk.PASSIVE
    )
    return authorize(agent_id, action, recorder=recorder, parent=parent)


def authorize_firestore_write(
    agent_id: str, tool: str, target: str, *, recorder: Any = None, parent: Any = None
) -> PermissionVerdict:
    action = ToolAction(
        tool=tool, target=target, risk=ActionRisk.INTERNAL_MUTATION
    )
    return authorize(agent_id, action, recorder=recorder, parent=parent)


def _record_denial(
    recorder: Any, parent: Any, agent_id: str, denial: CapabilityDenied
) -> None:
    if recorder is None:
        return
    with recorder.span(DENIAL_SPAN_NAME, parent=parent) as span:
        annotate_span(span, agent_id)
        span.set(ATTR_PERMISSION_DECISION, denial.verdict.decision.value)
        span.set(ATTR_AGENT_CAPABILITY, denial.verdict.tool)
        span.set("permission.target", denial.verdict.target)
        span.set("permission.reason", "; ".join(denial.verdict.reasons))
