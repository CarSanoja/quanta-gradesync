import pytest

from autocurricula.agents import proposer as proposer_module
from autocurricula.agents.proposer import LlmProposer, ProposalSchema
from autocurricula.core.evolution.prompt_mutator import PromptVariant
from autocurricula.schemas.metrics import CalibrationMetrics

pytestmark = pytest.mark.calibration

RATIONALE = "MAE 0.5 on factoring motivated an explicit mastery anchor."


async def test_llm_proposer_records_provenance_and_rationale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_structured_output(**kwargs) -> ProposalSchema:
        return ProposalSchema(
            new_system_instruction="Grade with evidence and mastery language.",
            new_few_shots=["Submission s1: calibrated scores factoring=4/4."],
            rationale=RATIONALE,
        )

    monkeypatch.setattr(
        proposer_module, "run_structured_output", fake_structured_output
    )
    current = PromptVariant(
        variant_id="grading-v1",
        version=3,
        system_instruction="Grade fairly against the rubric.",
        few_shots=[],
        provenance="seed",
    )
    metrics = CalibrationMetrics(
        mae=0.5,
        quadratic_weighted_kappa=0.4,
        bias=0.1,
        per_criterion={"factoring": 0.5},
    )
    proposer = LlmProposer("gemini-3.5-flash-lite")
    candidate = await proposer(current, metrics, attempt=1)
    assert candidate.version == 4
    assert candidate.provenance == "llm-proposer:grading-v1:v3:a1"
    assert proposer.proposal_log == [
        {"provenance": "llm-proposer:grading-v1:v3:a1", "rationale": RATIONALE}
    ]
