from collections.abc import Callable

from autocurricula.core.harness.actions import (
    ActionRisk,
    PermissionDecision,
    PermissionVerdict,
    ToolAction,
)

Rule = Callable[[ToolAction], PermissionDecision | None]


class PermissionRuleError(ValueError):
    pass


class PermissionGate:
    def __init__(self, rules: list[Rule]) -> None:
        if not rules:
            raise PermissionRuleError("permission gate requires at least one rule")
        self._rules = list(rules)

    def evaluate(self, action: ToolAction) -> PermissionVerdict:
        for decision in (PermissionDecision.DENY, PermissionDecision.QUARANTINE):
            for rule in self._rules:
                outcome = rule(action)
                if outcome == decision:
                    return PermissionVerdict(
                        decision=decision,
                        tool=action.tool,
                        target=action.target,
                        reasons=[_reason_for(decision, action)],
                    )
        return PermissionVerdict(
            decision=PermissionDecision.ALLOW,
            tool=action.tool,
            target=action.target,
        )


def _reason_for(decision: PermissionDecision, action: ToolAction) -> str:
    if decision == PermissionDecision.DENY:
        return f"target {action.target!r} is outside the allowed scope for {action.tool}"
    return (
        f"external mutation {action.tool} for {action.target!r} did not clear "
        "the confidence gate"
    )


def scope_rule(tool: str, allowed_targets: set[str]) -> Rule:
    def rule(action: ToolAction) -> PermissionDecision | None:
        if action.tool != tool:
            return None
        if action.target in allowed_targets:
            return None
        return PermissionDecision.DENY

    return rule


def confidence_rule(tool: str, confidence_key: str, threshold: float) -> Rule:
    def rule(action: ToolAction) -> PermissionDecision | None:
        if action.tool != tool or action.risk != ActionRisk.EXTERNAL_MUTATION:
            return None
        confidence = action.payload.get(confidence_key)
        if isinstance(confidence, (int, float)) and float(confidence) >= threshold:
            return None
        return PermissionDecision.QUARANTINE

    return rule


def manifest_scope_gate(
    allowed_targets: set[str], tool: str, confidence_key: str, threshold: float
) -> PermissionGate:
    return PermissionGate(
        [
            scope_rule(tool, allowed_targets),
            confidence_rule(tool, confidence_key, threshold),
        ]
    )
