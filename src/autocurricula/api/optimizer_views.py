from collections.abc import Callable
from typing import Any

from pydantic import Field, ValidationError

from autocurricula.agents.prompts import (
    AUDITOR_VARIANT_ID,
    GRADING_VARIANT_ID,
    build_auditor_variant,
    build_grading_prompt_variant,
)
from autocurricula.core.evolution.prompt_mutator import PromptVariant
from autocurricula.schemas.common import StrictBaseModel
from autocurricula.schemas.metrics import CalibrationMetrics, OptimizerReport

SOURCE_REGISTRY = "registry"
SOURCE_HISTORY = "history"
SOURCE_SEED = "seed"

SEED_BUILDERS: dict[str, Callable[[], PromptVariant]] = {
    GRADING_VARIANT_ID: build_grading_prompt_variant,
    AUDITOR_VARIANT_ID: build_auditor_variant,
}


class OptimizerMetricsView(StrictBaseModel):
    mae: float
    quadratic_weighted_kappa: float
    bias: float


class OptimizerCycleView(StrictBaseModel):
    variant_id: str
    version: int
    recorded_at: str
    iteration: int
    accepted: bool
    delta_mae: float
    previous: OptimizerMetricsView
    candidate: OptimizerMetricsView
    rejected_reasons: list[str] = Field(default_factory=list)


class OptimizerVariantView(StrictBaseModel):
    variant_id: str
    active_version: int
    source: str
    provenance: str
    few_shot_count: int = Field(ge=0)
    system_instruction: str
    promoted_cycles: int = Field(ge=0)
    latest_metrics: OptimizerMetricsView | None = None


class OptimizerReportResponse(StrictBaseModel):
    variants: list[OptimizerVariantView] = Field(default_factory=list)
    cycles: list[OptimizerCycleView] = Field(default_factory=list)
    cycle_count: int = Field(ge=0)


def metrics_view(metrics: CalibrationMetrics) -> OptimizerMetricsView:
    return OptimizerMetricsView(
        mae=metrics.mae,
        quadratic_weighted_kappa=metrics.quadratic_weighted_kappa,
        bias=metrics.bias,
    )


def build_cycles(records: list[dict[str, Any]]) -> list[OptimizerCycleView]:
    cycles: list[OptimizerCycleView] = []
    for record in records:
        try:
            report = OptimizerReport.model_validate(record.get("report"))
        except ValidationError:
            continue
        cycles.append(
            OptimizerCycleView(
                variant_id=str(record.get("variant_id", "")),
                version=int(record.get("version", 0)),
                recorded_at=str(record.get("recorded_at", "")),
                iteration=report.iteration,
                accepted=report.accepted,
                delta_mae=report.delta_mae,
                previous=metrics_view(report.previous_metrics),
                candidate=metrics_view(report.candidate_metrics),
                rejected_reasons=list(report.rejected_reasons),
            )
        )
    return cycles


def _registry_variant(registry: Any, variant_id: str) -> PromptVariant | None:
    try:
        return registry.get(variant_id)
    except (ValueError, AttributeError):
        return None


def _promoted(record: dict[str, Any]) -> bool:
    report = record.get("report")
    if not isinstance(report, dict):
        return True
    return bool(report.get("accepted", True))


def _history_variant(records: list[dict[str, Any]], variant_id: str) -> PromptVariant | None:
    candidates: list[PromptVariant] = []
    for record in records:
        if record.get("variant_id") != variant_id or not _promoted(record):
            continue
        try:
            candidates.append(PromptVariant.from_dict(record["variant"]))
        except (KeyError, ValidationError):
            continue
    if not candidates:
        return None
    return max(candidates, key=lambda variant: variant.version)


def resolve_variant(
    registry: Any, variant_id: str, records: list[dict[str, Any]]
) -> tuple[PromptVariant, str] | None:
    from_history = _history_variant(records, variant_id)
    from_registry = _registry_variant(registry, variant_id)
    if from_history is not None and (
        from_registry is None or from_history.version >= from_registry.version
    ):
        return from_history, SOURCE_HISTORY
    if from_registry is not None:
        return from_registry, SOURCE_REGISTRY
    builder = SEED_BUILDERS.get(variant_id)
    if builder is None:
        return None
    return builder(), SOURCE_SEED


def build_variant_view(
    variant: PromptVariant,
    source: str,
    cycles: list[OptimizerCycleView],
) -> OptimizerVariantView:
    own = [cycle for cycle in cycles if cycle.variant_id == variant.variant_id]
    accepted = [cycle for cycle in own if cycle.accepted]
    return OptimizerVariantView(
        variant_id=variant.variant_id,
        active_version=variant.version,
        source=source,
        provenance=variant.provenance,
        few_shot_count=len(variant.few_shots),
        system_instruction=variant.system_instruction,
        promoted_cycles=len(accepted),
        latest_metrics=accepted[-1].candidate if accepted else None,
    )
