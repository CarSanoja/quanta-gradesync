from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

from autocurricula.core.harness.actions import (
    PermissionDecision,
    PermissionVerdict,
    ToolAction,
)
from autocurricula.core.harness.permission_gate import PermissionGate, Rule
from autocurricula.schemas.common import utc_now
from autocurricula.schemas.fleet import CapabilityAuditRecord

CapabilityResolver = Callable[[ToolAction], str | None]

UNKNOWN_AGENT_REASON = "agent {agent_id!r} is not declared in the fleet registry"
UNMAPPED_TOOL_REASON = "tool {tool!r} maps to no declared capability; failing closed"
MISSING_CAPABILITY_REASON = (
    "agent {agent_id!r} (principal {principal_id!r}) does not hold capability "
    "{capability!r} required by {tool!r}"
)


@dataclass(frozen=True)
class AgentGrant:
    agent_id: str
    principal_id: str
    capabilities: frozenset[str]

    def holds(self, capability: str) -> bool:
        return capability in self.capabilities


class CapabilityDenied(PermissionError):
    def __init__(self, agent_id: str, verdict: PermissionVerdict) -> None:
        super().__init__(
            f"capability gate denied {verdict.tool} on {verdict.target!r} for "
            f"agent {agent_id}: {'; '.join(verdict.reasons)}"
        )
        self.agent_id = agent_id
        self.verdict = verdict


@dataclass
class CapabilityLedger:
    parent: "CapabilityLedger | None" = None
    records: list[CapabilityAuditRecord] = field(default_factory=list)

    def add(self, record: CapabilityAuditRecord) -> None:
        self.records.append(record)
        if self.parent is not None:
            self.parent.add(record)

    @property
    def denials(self) -> list[CapabilityAuditRecord]:
        return [
            record
            for record in self.records
            if record.decision == PermissionDecision.DENY.value
        ]


_current_ledger: ContextVar[CapabilityLedger | None] = ContextVar(
    "autocurricula_capability_ledger", default=None
)


@contextmanager
def capability_scope() -> Iterator[CapabilityLedger]:
    ledger = CapabilityLedger(parent=_current_ledger.get())
    token = _current_ledger.set(ledger)
    try:
        yield ledger
    finally:
        _current_ledger.reset(token)


def record_capability(record: CapabilityAuditRecord) -> None:
    ledger = _current_ledger.get()
    if ledger is not None:
        ledger.add(record)


def tool_capability_resolver(mapping: dict[str, str]) -> CapabilityResolver:
    frozen = dict(mapping)

    def resolve(action: ToolAction) -> str | None:
        return frozen.get(action.tool)

    return resolve


class AgentAuthorizer:
    def __init__(
        self, grants: Iterable[AgentGrant], resolver: CapabilityResolver
    ) -> None:
        self._grants = {grant.agent_id: grant for grant in grants}
        self._resolver = resolver

    @property
    def agent_ids(self) -> list[str]:
        return sorted(self._grants)

    @property
    def grants(self) -> list[AgentGrant]:
        return [self._grants[agent_id] for agent_id in self.agent_ids]

    def grant(self, agent_id: str) -> AgentGrant | None:
        return self._grants.get(agent_id)

    def evaluate(self, agent_id: str, action: ToolAction) -> PermissionVerdict:
        grant = self._grants.get(agent_id)
        if grant is None:
            return self._deny(action, UNKNOWN_AGENT_REASON.format(agent_id=agent_id))
        capability = self._resolver(action)
        if capability is None:
            return self._deny(action, UNMAPPED_TOOL_REASON.format(tool=action.tool))
        if not grant.holds(capability):
            return self._deny(
                action,
                MISSING_CAPABILITY_REASON.format(
                    agent_id=agent_id,
                    principal_id=grant.principal_id,
                    capability=capability,
                    tool=action.tool,
                ),
            )
        return PermissionVerdict(
            decision=PermissionDecision.ALLOW, tool=action.tool, target=action.target
        )

    def authorize(
        self, agent_id: str, action: ToolAction, *, gate: PermissionGate | None = None
    ) -> PermissionVerdict:
        verdict = self.evaluate(agent_id, action)
        if verdict.allowed and gate is not None:
            verdict = gate.evaluate(action)
        self.record(agent_id, action, verdict)
        if verdict.decision == PermissionDecision.DENY:
            raise CapabilityDenied(agent_id, verdict)
        return verdict

    def record(
        self, agent_id: str, action: ToolAction, verdict: PermissionVerdict
    ) -> CapabilityAuditRecord:
        grant = self._grants.get(agent_id)
        record = CapabilityAuditRecord(
            recorded_at=utc_now(),
            agent_id=agent_id,
            principal_id=grant.principal_id if grant is not None else "unknown",
            tool=action.tool,
            target=action.target,
            capability=self._resolver(action) or "",
            decision=verdict.decision.value,
            reasons=list(verdict.reasons),
        )
        record_capability(record)
        return record

    def capability_rule(self, agent_id: str) -> Rule:
        def rule(action: ToolAction) -> PermissionDecision | None:
            verdict = self.evaluate(agent_id, action)
            return None if verdict.allowed else verdict.decision

        rule.permission_reason = lambda action: "; ".join(  # type: ignore[attr-defined]
            self.evaluate(agent_id, action).reasons
        )
        return rule

    @staticmethod
    def _deny(action: ToolAction, reason: str) -> PermissionVerdict:
        return PermissionVerdict(
            decision=PermissionDecision.DENY,
            tool=action.tool,
            target=action.target,
            reasons=[reason],
        )
