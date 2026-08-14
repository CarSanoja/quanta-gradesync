import json
from pathlib import Path

import pytest

from autocurricula.agents.audit_calibration import LocalAuditEvaluator
from autocurricula.agents.audit_samples import audit_calibration_dir, build_audit_sample
from autocurricula.agents.optimizer_factory import build_meta_optimizer
from autocurricula.agents.prompt_variant_store import LocalPromptVariantStore
from autocurricula.core.evolution.calibration_store import CalibrationSet
from autocurricula.core.evolution.prompt_mutator import PromptVariant
from autocurricula.core.memory.manager import MemoryManager

pytestmark = pytest.mark.calibration

SUMMARY_A = "el estudiante modela situaciones algebraicas usando graficas"
SUMMARY_B = "la estudiante argumenta variaciones proporcionales con tablas"
ITEMS_A = ("crit-a->MAT.8.1", "crit-b->MAT.8.2")
ITEMS_B = ("crit-c->MAT.8.3", "crit-d->MAT.8.4")


def stage_audit_calibration(settings) -> Path:
    directory = audit_calibration_dir(settings)
    directory.mkdir(parents=True, exist_ok=True)
    for submission_id, summary in (
        ("aud-001", SUMMARY_A),
        ("aud-002", SUMMARY_B),
    ):
        items = ITEMS_A if submission_id == "aud-001" else ITEMS_B
        sample = build_audit_sample(
            submission_id,
            summary,
            {item.split("->")[0]: [item.split("->")[1]] for item in items},
        ).samples[0]
        (directory / f"{submission_id}.json").write_text(
            sample.model_dump_json(), encoding="utf-8"
        )
    return directory


class EnrichingProposer:
    def __init__(self, candidate: PromptVariant) -> None:
        self._candidate = candidate

    async def __call__(self, current, metrics, attempt: int = 0) -> PromptVariant:
        return self._candidate


def enriched_variant(base: PromptVariant) -> PromptVariant:
    shots = list(base.few_shots)
    shots.append(
        f"aud-001: {SUMMARY_A} — mapping crit-a->MAT.8.1 verificado"
    )
    shots.append(f"aud-002: {SUMMARY_B} — mapping crit-c->MAT.8.3 verificado")
    return PromptVariant(
        variant_id=base.variant_id,
        version=base.version + 1,
        system_instruction=f"{base.system_instruction}\nCite exact mapping codes.",
        few_shots=shots,
        provenance="test-enriched",
    )


def flat_variant(base: PromptVariant, marker: str) -> PromptVariant:
    return PromptVariant(
        variant_id=base.variant_id,
        version=base.version + 1,
        system_instruction=f"{base.system_instruction}\n{marker}",
        few_shots=list(base.few_shots),
        provenance="test-flat",
    )


async def test_local_audit_evaluator_rewards_cited_mappings(settings) -> None:
    directory = stage_audit_calibration(settings)
    calibration = CalibrationSet.from_directory(directory)
    from autocurricula.agents.prompts import build_auditor_variant

    base = build_auditor_variant()
    evaluator = LocalAuditEvaluator()
    base_results = await evaluator(base, calibration)
    enriched_results = await evaluator(enriched_variant(base), calibration)

    base_scores = [s.score for r in base_results for s in r.criterion_scores]
    enriched_scores = [s.score for r in enriched_results for s in r.criterion_scores]
    assert max(base_scores) < 0.7
    assert max(enriched_scores) == pytest.approx(1.0)
    assert len(set(enriched_scores)) > 1
    assert sum(enriched_scores) / len(enriched_scores) > sum(base_scores) / len(
        base_scores
    )


async def test_auditor_scope_accepts_and_persists_improvement(settings) -> None:
    stage_audit_calibration(settings)
    from autocurricula.agents.prompts import build_auditor_variant

    memory_manager = MemoryManager.from_settings(settings)
    variant_store = LocalPromptVariantStore(settings.local_data_dir)
    base = build_auditor_variant()
    optimizer = build_meta_optimizer(
        settings,
        scope="auditor",
        memory_manager=memory_manager,
        proposer=EnrichingProposer(enriched_variant(base)),
        variant_store=variant_store,
    )

    winner = await optimizer.run_cycle()

    assert winner is not None
    assert winner.accepted is True
    history = optimizer.registry.history("auditor-v1")
    assert [variant.version for variant in history] == [1, 2]
    records = (settings.local_data_dir / "prompts" / "optimizer.jsonl").read_text(
        encoding="utf-8"
    ).splitlines()
    assert len(records) == 1
    assert json.loads(records[0])["variant_id"] == "auditor-v1"


async def test_auditor_scope_rejects_flat_candidate(settings) -> None:
    stage_audit_calibration(settings)
    from autocurricula.agents.prompts import build_auditor_variant

    memory_manager = MemoryManager.from_settings(settings)
    variant_store = LocalPromptVariantStore(settings.local_data_dir)
    base = build_auditor_variant()
    optimizer = build_meta_optimizer(
        settings,
        scope="auditor",
        memory_manager=memory_manager,
        proposer=EnrichingProposer(flat_variant(base, "flat marker")),
        variant_store=variant_store,
    )

    winner = await optimizer.run_cycle()

    assert winner is None
    assert len(optimizer.registry.history("auditor-v1")) == 1
    assert not (settings.local_data_dir / "prompts" / "optimizer.jsonl").exists()


def test_unknown_scope_is_rejected(settings) -> None:
    with pytest.raises(ValueError, match="unknown optimizer scope"):
        build_meta_optimizer(settings, scope="janitor")
