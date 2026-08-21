from typing import Any

from autocurricula.agents.prompts import (
    AUDITOR_VARIANT_ID,
    GRADING_VARIANT_ID,
    OPTIMIZER_VARIANT_ID,
    build_auditor_variant,
    build_grading_prompt_variant,
    seed_optimizer_variant,
)
from autocurricula.config.settings import Settings
from autocurricula.core.evolution.prompt_mutator import PromptVariant
from autocurricula.core.fleet.declarations import AgentDeclaration
from autocurricula.core.fleet.roster import (
    ARMOR_SCREENER_ID,
    CALIBRATION_EVALUATOR_ID,
    CURRICULUM_AUDITOR_ID,
    FALLBACK_EVALUATOR_ID,
    GRADING_AGENT_ID,
    META_OPTIMIZER_AUDIT_ID,
    META_OPTIMIZER_GRADING_ID,
    OPTIMIZER_AGENTS,
    PROMPT_PROPOSER_ID,
    RISK_DETECTOR_ID,
    SCHEMA_REPAIR_ID,
    SECOND_OPINION_ID,
)

UNWIRED_BINDING = "unwired"
DETERMINISTIC_MODEL = "deterministic"
LOCAL_MODEL = "local-deterministic"
DETERMINISTIC_PREFIXES = ("Local", "Scripted")
DETERMINISTIC_BINDINGS = frozenset(
    {"RiskDetector", "SchemaRepairAgent", "MetaOptimizerAgent"}
)

LOCAL_UNWIRED_AGENTS = frozenset({SECOND_OPINION_ID, FALLBACK_EVALUATOR_ID})

SETTINGS_BINDINGS: dict[str, tuple[str, str]] = {
    GRADING_AGENT_ID: ("AdkGradingEvaluator", "AdkGradingEvaluator"),
    CURRICULUM_AUDITOR_ID: ("AdkCurriculumAuditor", "LocalCurriculumAuditor"),
    RISK_DETECTOR_ID: ("RiskDetector", "RiskDetector"),
    SECOND_OPINION_ID: ("AdkGradingEvaluator", UNWIRED_BINDING),
    FALLBACK_EVALUATOR_ID: ("AdkGradingEvaluator", UNWIRED_BINDING),
    ARMOR_SCREENER_ID: ("LlmInjectionDetector", "ScriptedInjectionDetector"),
    SCHEMA_REPAIR_ID: ("SchemaRepairAgent", "SchemaRepairAgent"),
    PROMPT_PROPOSER_ID: ("LlmProposer", "LocalHeuristicProposer"),
    CALIBRATION_EVALUATOR_ID: ("AdkSummaryGradingEvaluator", "LocalGradingEvaluator"),
    META_OPTIMIZER_GRADING_ID: ("MetaOptimizerAgent", "MetaOptimizerAgent"),
    META_OPTIMIZER_AUDIT_ID: ("MetaOptimizerAgent", "MetaOptimizerAgent"),
}

SEED_VARIANTS = {
    GRADING_VARIANT_ID: build_grading_prompt_variant,
    AUDITOR_VARIANT_ID: build_auditor_variant,
    OPTIMIZER_VARIANT_ID: seed_optimizer_variant,
}


def is_deterministic_binding(name: str) -> bool:
    return name in DETERMINISTIC_BINDINGS or name.startswith(DETERMINISTIC_PREFIXES)


def optimizer_for(container: Any, variant_id: str) -> Any:
    for optimizer in getattr(container, "optimizers", None) or []:
        if getattr(optimizer, "variant_id", None) == variant_id:
            return optimizer
    return None


def has_container_source(declaration: AgentDeclaration) -> bool:
    return (
        declaration.container_attr is not None
        or declaration.agent_id in OPTIMIZER_AGENTS
    )


def wired_object(declaration: AgentDeclaration, container: Any) -> Any:
    if container is None:
        return None
    variant_id = OPTIMIZER_AGENTS.get(declaration.agent_id)
    if variant_id is not None:
        return optimizer_for(container, variant_id)
    if declaration.container_attr is None:
        return None
    return getattr(container, declaration.container_attr, None)


def settings_binding(declaration: AgentDeclaration, settings: Settings) -> str:
    names = SETTINGS_BINDINGS.get(declaration.agent_id)
    if names is None:
        return UNWIRED_BINDING
    return names[1] if settings.local_mode else names[0]


def declared_wired(declaration: AgentDeclaration, settings: Settings) -> bool:
    if declaration.agent_id == ARMOR_SCREENER_ID:
        return settings.armor_enabled
    if declaration.agent_id in LOCAL_UNWIRED_AGENTS:
        return not settings.local_mode
    return True


def registry_variants(container: Any) -> dict[str, PromptVariant]:
    variants: dict[str, PromptVariant] = {}
    for optimizer in getattr(container, "optimizers", None) or []:
        registry = getattr(optimizer, "registry", None)
        if registry is None:
            continue
        for variant_id in (GRADING_VARIANT_ID, AUDITOR_VARIANT_ID, OPTIMIZER_VARIANT_ID):
            if variant_id in variants:
                continue
            try:
                variants[variant_id] = registry.get(variant_id)
            except (ValueError, KeyError, AttributeError):
                continue
    return variants


def seed_variant(variant_id: str) -> PromptVariant | None:
    builder = SEED_VARIANTS.get(variant_id)
    return None if builder is None else builder()
