import pytest

from autocurricula.agents.audit_samples import build_audit_sample
from autocurricula.agents.optimizer_factory import build_meta_optimizer
from autocurricula.agents.prompt_variant_store import LocalPromptVariantStore
from autocurricula.agents.prompts import build_auditor_variant
from autocurricula.core.evolution.calibration_store import CalibrationSet
from autocurricula.core.evolution.prompt_mutator import PromptVariant
from autocurricula.core.memory.manager import MemoryManager
from autocurricula.schemas.grading import CriterionScore, GradingResult

pytestmark = pytest.mark.calibration

SUMMARY_A = "el estudiante modela situaciones algebraicas usando graficas"
SUMMARY_B = "la estudiante argumenta variaciones proporcionales con tablas"


def stage_calibration(settings) -> CalibrationSet:
    directory = settings.local_data_dir / "calibration_audits"
    directory.mkdir(parents=True, exist_ok=True)
    samples = []
    for submission_id, summary in (("aud-001", SUMMARY_A), ("aud-002", SUMMARY_B)):
        sample = build_audit_sample(
            submission_id,
            summary,
            {"crit-a": ["MAT.8.1"], "crit-b": ["MAT.8.2"]},
        ).samples[0]
        (directory / f"{submission_id}.json").write_text(
            sample.model_dump_json(), encoding="utf-8"
        )
        samples.append(sample)
    return CalibrationSet(samples)


class ScoreProfileEvaluator:
    def __init__(self, score_by_instruction: dict[str, tuple[float, float]]) -> None:
        self._scores = score_by_instruction

    async def __call__(self, variant, calibration) -> list[GradingResult]:
        low, high = self._scores[variant.system_instruction]
        results = []
        for index, sample in enumerate(calibration):
            first, second = (low, high) if index % 2 == 0 else (high, low)
            results.append(
                GradingResult(
                    submission_id=sample.submission_id,
                    criterion_scores=[
                        CriterionScore(
                            criterion_id=expected.criterion_id,
                            score=score,
                            comment="scripted agreement",
                            confidence=0.9,
                        )
                        for expected, score in zip(sample.expected, (first, second))
                    ],
                    total_score=round(first + second, 4),
                    percentage=round(100.0 * (first + second) / 2, 2),
                    feedback="scripted",
                )
            )
        return results


class SequenceProposer:
    def __init__(self, instructions: list[str]) -> None:
        self._instructions = instructions
        self.calls = 0

    async def __call__(self, current, metrics, attempt: int = 0) -> PromptVariant:
        instruction = self._instructions[
            min(self.calls, len(self._instructions) - 1)
        ]
        self.calls += 1
        return PromptVariant(
            variant_id=current.variant_id,
            version=current.version + 1,
            system_instruction=instruction,
            few_shots=list(current.few_shots),
            provenance="sequence",
        )


def profiles(base: str, candidates: list[tuple[str, tuple[float, float]]]):
    score_map = {base: (0.2, 0.3)}
    for instruction, scores in candidates:
        score_map[instruction] = scores
    return score_map


def build_optimizer(settings, proposer, evaluator):
    return build_meta_optimizer(
        settings,
        scope="auditor",
        memory_manager=MemoryManager.from_settings(settings),
        proposer=proposer,
        evaluator=evaluator,
        variant_store=LocalPromptVariantStore(settings.local_data_dir),
    )


async def test_convergence_stops_on_marginal_improvement(settings) -> None:
    stage_calibration(settings)
    base = build_auditor_variant()
    big = "mutation with large agreement gain"
    tiny = "mutation with marginal agreement gain"
    evaluator = ScoreProfileEvaluator(
        profiles(
            base.system_instruction,
            [(big, (0.70, 0.80)), (tiny, (0.705, 0.805))],
        )
    )
    single_candidate = settings.model_copy(update={"optimizer_candidates": 1})
    optimizer = build_optimizer(
        single_candidate, SequenceProposer([big, tiny]), evaluator
    )

    winners = await optimizer.run_until_convergence()

    assert len(winners) == 2
    first, second = winners
    assert first.previous_metrics.mae - first.candidate_metrics.mae == pytest.approx(0.5)
    assert second.previous_metrics.mae - second.candidate_metrics.mae < 0.01
    versions = [v.version for v in optimizer.registry.history("auditor-v1")]
    assert versions == [1, 2, 3]


async def test_convergence_stops_when_cycle_accepts_nothing(settings) -> None:
    stage_calibration(settings)
    base = build_auditor_variant()
    flat = "flat mutation without agreement gain"
    evaluator = ScoreProfileEvaluator(
        profiles(base.system_instruction, [(flat, (0.2, 0.3))])
    )
    optimizer = build_optimizer(settings, SequenceProposer([flat]), evaluator)

    winners = await optimizer.run_until_convergence()

    assert winners == []
    assert len(optimizer.registry.history("auditor-v1")) == 1


async def test_convergence_respects_cycle_budget(settings) -> None:
    stage_calibration(settings)
    base = build_auditor_variant()
    candidates = [
        ("steady mutation one", (0.70, 0.80)),
        ("steady mutation two", (0.80, 0.90)),
        ("steady mutation three", (0.90, 0.95)),
        ("steady mutation four", (0.95, 0.975)),
    ]
    evaluator = ScoreProfileEvaluator(
        profiles(base.system_instruction, candidates)
    )
    bounded = settings.model_copy(update={"optimizer_max_cycles": 2})
    optimizer = build_optimizer(
        bounded, SequenceProposer([name for name, _ in candidates]), evaluator
    )

    winners = await optimizer.run_until_convergence()

    assert len(winners) == 2
    assert all(
        winner.previous_metrics.mae - winner.candidate_metrics.mae >= 0.01
        for winner in winners
    )
    assert len(optimizer.registry.history("auditor-v1")) == 3
