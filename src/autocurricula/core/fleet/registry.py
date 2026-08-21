import hashlib
import json
from collections import Counter
from typing import Any

from autocurricula.config.settings import Settings
from autocurricula.core.fleet.bindings import (
    DETERMINISTIC_MODEL,
    LOCAL_MODEL,
    UNWIRED_BINDING,
    declared_wired,
    has_container_source,
    is_deterministic_binding,
    registry_variants,
    seed_variant,
    settings_binding,
    wired_object,
)
from autocurricula.core.fleet.declarations import AgentDeclaration
from autocurricula.core.fleet.identity import all_principals, build_agent_principal
from autocurricula.core.fleet.roster import AGENT_DECLARATIONS
from autocurricula.core.harness.provenance import prompt_version_sha
from autocurricula.schemas.common import utc_now
from autocurricula.schemas.fleet import (
    AgentDescriptor,
    FieldSource,
    FleetRegistryResponse,
    FleetSummary,
    PromptBinding,
)

SOURCE_REGISTRY = "registry"
SOURCE_SEED = "seed"

FIELD_SOURCES: dict[str, FieldSource] = {
    "agent_id": FieldSource.DECLARED,
    "display_name": FieldSource.DECLARED,
    "role": FieldSource.DECLARED,
    "stages": FieldSource.DECLARED,
    "lifecycle": FieldSource.DECLARED,
    "capabilities": FieldSource.DECLARED,
    "principal.service_account": FieldSource.SETTINGS,
    "definition_sha": FieldSource.COMPUTED,
}


def _sha256(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _model_of(
    declaration: AgentDeclaration, settings: Settings, binding: str, obj: Any
) -> tuple[str, FieldSource]:
    for attribute in ("model", "model_id"):
        value = getattr(obj, attribute, None)
        if isinstance(value, str) and value.strip():
            return value.strip(), FieldSource.CONTAINER
    if is_deterministic_binding(binding):
        return (
            LOCAL_MODEL if binding.startswith(("Local", "Scripted")) else DETERMINISTIC_MODEL,
            FieldSource.SETTINGS,
        )
    if declaration.model_setting is not None:
        return str(getattr(settings, declaration.model_setting)), FieldSource.SETTINGS
    return DETERMINISTIC_MODEL, FieldSource.DECLARED


def _prompt_of(
    declaration: AgentDeclaration, variants: dict[str, Any]
) -> tuple[PromptBinding | None, FieldSource]:
    variant_id = declaration.prompt_variant_id
    if variant_id is None:
        return None, FieldSource.DECLARED
    variant = variants.get(variant_id)
    source = SOURCE_REGISTRY
    if variant is None:
        variant = seed_variant(variant_id)
        source = SOURCE_SEED
    if variant is None:
        return None, FieldSource.DECLARED
    binding = PromptBinding(
        variant_id=variant.variant_id,
        version=variant.version,
        version_sha=prompt_version_sha(variant),
        source=source,
    )
    field_source = (
        FieldSource.PROMPT_STORE if source == SOURCE_REGISTRY else FieldSource.DECLARED
    )
    return binding, field_source


def _definition_sha(descriptor: dict[str, Any]) -> str:
    return _sha256(json.dumps(descriptor, ensure_ascii=False, sort_keys=True))


def build_descriptor(
    declaration: AgentDeclaration,
    settings: Settings,
    container: Any,
    variants: dict[str, Any],
) -> AgentDescriptor:
    obj = wired_object(declaration, container)
    from_container = container is not None and has_container_source(declaration)
    wired = obj is not None if from_container else declared_wired(declaration, settings)
    binding = type(obj).__name__ if obj is not None else settings_binding(declaration, settings)
    if not wired:
        binding = UNWIRED_BINDING
    model_id, model_source = _model_of(declaration, settings, binding, obj)
    prompt, prompt_source = _prompt_of(declaration, variants)
    principal = build_agent_principal(settings, declaration)
    sources = dict(FIELD_SOURCES)
    sources["model_id"] = model_source
    sources["runtime_binding"] = (
        FieldSource.CONTAINER if obj is not None else FieldSource.SETTINGS
    )
    sources["wired"] = FieldSource.CONTAINER if from_container else FieldSource.SETTINGS
    sources["prompt"] = prompt_source
    payload = {
        "agent_id": declaration.agent_id,
        "display_name": declaration.display_name,
        "role": declaration.role,
        "model_id": model_id,
        "stages": list(declaration.stages),
        "runtime_binding": binding,
        "lifecycle": declaration.lifecycle.value,
        "principal": principal.model_dump(mode="json"),
        "prompt": prompt.model_dump(mode="json") if prompt is not None else None,
    }
    return AgentDescriptor(
        **payload,
        model_source=model_source,
        fleet_index=declaration.fleet_index,
        wired=wired,
        definition_sha=_definition_sha(payload),
        field_sources=sources,
    )


def build_fleet_registry(
    settings: Settings, container: Any = None
) -> FleetRegistryResponse:
    variants = registry_variants(container)
    agents = [
        build_descriptor(declaration, settings, container, variants)
        for declaration in AGENT_DECLARATIONS
    ]
    principals = all_principals(settings)
    stages = Counter(stage for agent in agents for stage in agent.stages)
    summary = FleetSummary(
        mode="local" if settings.local_mode else "gcp",
        agent_count=len(agents),
        wired_count=sum(1 for agent in agents if agent.wired),
        principal_count=len(principals),
        dedicated_service_accounts=sum(
            1 for principal in principals if principal.dedicated_service_account
        ),
        by_model=dict(sorted(Counter(agent.model_id for agent in agents).items())),
        by_lifecycle=dict(
            sorted(Counter(agent.lifecycle.value for agent in agents).items())
        ),
        by_stage=dict(sorted(stages.items())),
        registry_sha=_sha256("|".join(agent.definition_sha for agent in agents)),
    )
    return FleetRegistryResponse(
        generated_at=utc_now(),
        agents=agents,
        principals=principals,
        summary=summary,
    )
