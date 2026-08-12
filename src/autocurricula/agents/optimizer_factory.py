from collections.abc import Callable
from pathlib import Path

from autocurricula.agents.audit_calibration import build_audit_evaluator
from autocurricula.agents.audit_samples import audit_calibration_dir
from autocurricula.agents.base import resolve_model
from autocurricula.agents.calibration_evaluator import build_calibration_evaluator
from autocurricula.agents.local_proposer import LocalHeuristicProposer
from autocurricula.agents.meta_optimizer import MetaOptimizerAgent
from autocurricula.agents.prompt_variant_store import (
    PromptVariantStore,
    build_prompt_variant_store,
)
from autocurricula.agents.prompts import (
    AUDITOR_VARIANT_ID,
    GRADING_VARIANT_ID,
)
from autocurricula.agents.proposer import LlmProposer
from autocurricula.config.settings import Settings, get_settings
from autocurricula.core.evolution.optimizer_engine import (
    PromptProposer,
    VariantEvaluator,
)
from autocurricula.core.evolution.prompt_mutator import PromptRegistry
from autocurricula.core.harness.eval_harness import (
    ObjectiveGate,
    ObjectiveThresholds,
)
from autocurricula.core.memory.manager import MemoryManager

__all__ = [
    "LlmProposer",
    "build_meta_optimizer",
    "build_optimizer_fleet",
    "build_proposer",
]

VariantSeeder = Callable[[PromptRegistry], object]


def build_proposer(settings: Settings) -> PromptProposer:
    if settings.local_mode:
        return LocalHeuristicProposer()
    return LlmProposer(resolve_model(settings, "gemini_flash_model"))


def build_objective_gate(settings: Settings, scope: str) -> ObjectiveGate | None:
    if not settings.objective_gate_enabled:
        return None
    if scope == "auditor":
        thresholds = ObjectiveThresholds(
            qwk_min=None,
            mae_max=settings.objective_mae_max,
            bias_abs_max=0.3,
        )
    else:
        thresholds = ObjectiveThresholds(
            qwk_min=settings.objective_qwk_min,
            mae_max=settings.objective_mae_max,
            bias_abs_max=settings.objective_bias_abs_max,
        )
    return ObjectiveGate(thresholds)


def build_meta_optimizer(
    settings: Settings | None = None,
    *,
    scope: str = "grading",
    memory_manager: MemoryManager | None = None,
    proposer: PromptProposer | None = None,
    evaluator: VariantEvaluator | None = None,
    registry: PromptRegistry | None = None,
    variant_store: PromptVariantStore | None = None,
    calibration_dir: Path | None = None,
    metrics_threshold: float = 0.0,
) -> MetaOptimizerAgent:
    resolved = settings if settings is not None else get_settings()
    if scope == "grading":
        variant_id = GRADING_VARIANT_ID
        resolved_evaluator = (
            evaluator if evaluator is not None else build_calibration_evaluator(resolved)
        )
        resolved_dir = calibration_dir
    elif scope == "auditor":
        variant_id = AUDITOR_VARIANT_ID
        resolved_evaluator = (
            evaluator if evaluator is not None else build_audit_evaluator(resolved)
        )
        resolved_dir = (
            calibration_dir
            if calibration_dir is not None
            else audit_calibration_dir(resolved)
        )
    else:
        raise ValueError(f"unknown optimizer scope {scope!r}")
    return MetaOptimizerAgent(
        memory_manager=(
            memory_manager
            if memory_manager is not None
            else MemoryManager.from_settings(resolved)
        ),
        proposer=proposer if proposer is not None else build_proposer(resolved),
        evaluator=resolved_evaluator,
        registry=registry,
        variant_store=(
            variant_store
            if variant_store is not None
            else build_prompt_variant_store(resolved)
        ),
        calibration_dir=resolved_dir,
        metrics_threshold=metrics_threshold,
        candidate_count=resolved.optimizer_candidates,
        convergence_min_improvement=resolved.optimizer_convergence_min_improvement,
        max_cycles=resolved.optimizer_max_cycles,
        variance_collapse_ratio=resolved.variance_collapse_ratio,
        objective_gate=build_objective_gate(resolved, scope),
        variant_id=variant_id,
    )


def build_optimizer_fleet(
    settings: Settings | None = None,
    *,
    memory_manager: MemoryManager | None = None,
) -> list[MetaOptimizerAgent]:
    return [
        build_meta_optimizer(settings, scope="grading", memory_manager=memory_manager),
        build_meta_optimizer(settings, scope="auditor", memory_manager=memory_manager),
    ]
