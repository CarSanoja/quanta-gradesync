import pytest

from autocurricula.core.harness import (
    ActionRisk,
    BatchAnomalyBreaker,
    BreakerTripped,
    PermissionDecision,
    manifest_scope_gate,
)
from autocurricula.core.harness.actions import ToolAction

SIS_TOOL = "sis.write_grades"


def action(target: str, confidence: float) -> ToolAction:
    return ToolAction(
        tool=SIS_TOOL,
        target=target,
        risk=ActionRisk.EXTERNAL_MUTATION,
        payload={"min_confidence": confidence},
    )


def test_in_manifest_above_threshold_is_allowed() -> None:
    gate = manifest_scope_gate({"stu-1"}, SIS_TOOL, "min_confidence", 0.85)
    assert gate.evaluate(action("stu-1", 0.9)).decision == PermissionDecision.ALLOW


def test_out_of_manifest_target_is_denied_before_network() -> None:
    gate = manifest_scope_gate({"stu-1"}, SIS_TOOL, "min_confidence", 0.85)
    verdict = gate.evaluate(action("stu-7", 0.99))
    assert verdict.decision == PermissionDecision.DENY
    assert "outside the allowed scope" in verdict.reasons[0]


def test_below_threshold_is_quarantined_not_denied() -> None:
    gate = manifest_scope_gate({"stu-1"}, SIS_TOOL, "min_confidence", 0.85)
    verdict = gate.evaluate(action("stu-1", 0.6))
    assert verdict.decision == PermissionDecision.QUARANTINE
    assert "confidence gate" in verdict.reasons[0]


def test_boundary_confidence_is_allowed() -> None:
    gate = manifest_scope_gate({"stu-1"}, SIS_TOOL, "min_confidence", 0.85)
    assert gate.evaluate(action("stu-1", 0.85)).decision == PermissionDecision.ALLOW


def test_deny_takes_priority_over_quarantine() -> None:
    gate = manifest_scope_gate(set(), SIS_TOOL, "min_confidence", 0.85)
    verdict = gate.evaluate(action("stu-9", 0.1))
    assert verdict.decision == PermissionDecision.DENY


def test_passive_actions_of_other_tools_are_ignored() -> None:
    gate = manifest_scope_gate({"stu-1"}, SIS_TOOL, "min_confidence", 0.85)
    read = ToolAction(tool="gcs.fetch", target="obj", risk=ActionRisk.PASSIVE)
    assert gate.evaluate(read).decision == PermissionDecision.ALLOW


def test_batch_anomaly_breaker_trips_above_threshold() -> None:
    breaker = BatchAnomalyBreaker(threshold=0.15)
    with pytest.raises(BreakerTripped, match="quarantine ratio"):
        breaker.evaluate(total=40, quarantined=7)


def test_batch_anomaly_breaker_passes_at_or_below_threshold() -> None:
    breaker = BatchAnomalyBreaker(threshold=0.15)
    assert breaker.evaluate(total=40, quarantined=6).ratio == pytest.approx(0.15)
    assert breaker.evaluate(total=40, quarantined=2).quarantined == 2


def test_batch_anomaly_breaker_rejects_invalid_threshold() -> None:
    with pytest.raises(ValueError):
        BatchAnomalyBreaker(threshold=0.0)


def test_batch_anomaly_breaker_rejects_inconsistent_counts() -> None:
    breaker = BatchAnomalyBreaker()
    with pytest.raises(ValueError):
        breaker.ratio(total=3, quarantined=5)
