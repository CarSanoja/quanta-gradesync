import pytest

from autocurricula.core.fleet import (
    SIS_WRITER_PRINCIPAL,
    build_default_authorizer,
    get_authorizer,
    reset_authorizer_cache,
)
from autocurricula.core.fleet.declarations import LLM_GENERATE, SIS_WRITE_GRADES
from autocurricula.core.fleet.roster import GRADING_AGENT_ID, RISK_DETECTOR_ID
from autocurricula.core.harness import (
    ActionRisk,
    CapabilityDenied,
    PermissionDecision,
    PermissionGate,
    ToolAction,
    capability_scope,
)


@pytest.fixture(autouse=True)
def fresh_authorizer():
    reset_authorizer_cache()
    yield
    reset_authorizer_cache()


def llm_action(target: str = "sub-1") -> ToolAction:
    return ToolAction(tool=LLM_GENERATE, target=target, risk=ActionRisk.PASSIVE)


def sis_action(target: str = "stu-1") -> ToolAction:
    return ToolAction(
        tool=SIS_WRITE_GRADES,
        target=target,
        risk=ActionRisk.EXTERNAL_MUTATION,
        payload={"min_confidence": 0.99},
    )


def test_declared_capability_is_allowed() -> None:
    verdict = build_default_authorizer().evaluate(GRADING_AGENT_ID, llm_action())

    assert verdict.decision == PermissionDecision.ALLOW


def test_out_of_scope_action_is_denied_before_any_call() -> None:
    authorizer = build_default_authorizer()

    verdict = authorizer.evaluate(GRADING_AGENT_ID, sis_action())

    assert verdict.decision == PermissionDecision.DENY
    assert "sis.write" in verdict.reasons[0]
    assert GRADING_AGENT_ID in verdict.reasons[0]


def test_denied_action_raises_and_is_recorded_in_the_ledger() -> None:
    authorizer = build_default_authorizer()

    with capability_scope() as ledger:
        with pytest.raises(CapabilityDenied):
            authorizer.authorize(RISK_DETECTOR_ID, llm_action("sub-9"))

    assert len(ledger.denials) == 1
    record = ledger.denials[0]
    assert record.agent_id == RISK_DETECTOR_ID
    assert record.principal_id == f"agent://{RISK_DETECTOR_ID}"
    assert record.tool == LLM_GENERATE
    assert record.target == "sub-9"
    assert record.capability == "llm.invoke"
    assert record.decision == PermissionDecision.DENY.value


def test_allowed_action_is_also_recorded_for_attribution() -> None:
    authorizer = build_default_authorizer()

    with capability_scope() as ledger:
        authorizer.authorize(GRADING_AGENT_ID, llm_action("sub-2"))

    assert ledger.denials == []
    assert ledger.records[0].decision == PermissionDecision.ALLOW.value
    assert ledger.records[0].principal_id == f"agent://{GRADING_AGENT_ID}"


def test_unknown_agent_is_denied() -> None:
    verdict = build_default_authorizer().evaluate("ghost-agent", llm_action())

    assert verdict.decision == PermissionDecision.DENY
    assert "not declared in the fleet registry" in verdict.reasons[0]


def test_unmapped_tool_fails_closed() -> None:
    action = ToolAction(
        tool="bigquery.export", target="dataset", risk=ActionRisk.EXTERNAL_MUTATION
    )

    verdict = build_default_authorizer().evaluate(GRADING_AGENT_ID, action)

    assert verdict.decision == PermissionDecision.DENY
    assert "no declared capability" in verdict.reasons[0]


def test_capability_rule_composes_into_the_permission_gate() -> None:
    authorizer = build_default_authorizer()
    gate = PermissionGate([authorizer.capability_rule(GRADING_AGENT_ID)])

    verdict = gate.evaluate(sis_action())

    assert verdict.decision == PermissionDecision.DENY
    assert "does not hold capability 'sis.write'" in verdict.reasons[0]


def test_sis_writer_principal_holds_the_write_capability() -> None:
    verdict = get_authorizer().evaluate(SIS_WRITER_PRINCIPAL, sis_action())

    assert verdict.decision == PermissionDecision.ALLOW
