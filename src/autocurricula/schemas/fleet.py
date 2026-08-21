from enum import StrEnum

from pydantic import Field

from autocurricula.schemas.common import FrozenStrictModel, StrictBaseModel, TzAwareDatetime
from autocurricula.schemas.provenance import SHA256Hex


class AgentLifecycle(StrEnum):
    ACTIVE = "active"
    SHADOW = "shadow"
    RETIRED = "retired"


class Capability(StrEnum):
    LLM_INVOKE = "llm.invoke"
    GCS_READ = "gcs.read"
    GCS_WRITE = "gcs.write"
    FIRESTORE_READ = "firestore.read"
    FIRESTORE_WRITE = "firestore.write"
    SIS_WRITE = "sis.write"
    PUBSUB_PUBLISH = "pubsub.publish"


class FieldSource(StrEnum):
    DECLARED = "declared"
    SETTINGS = "settings"
    CONTAINER = "container"
    PROMPT_STORE = "prompt_store"
    COMPUTED = "computed"


class AgentPrincipal(FrozenStrictModel):
    principal_id: str = Field(min_length=1)
    description: str = ""
    service_account: str = Field(min_length=1)
    dedicated_service_account: bool = False
    impersonated: bool = False
    capabilities: list[Capability] = Field(default_factory=list)


class PromptBinding(FrozenStrictModel):
    variant_id: str = Field(min_length=1)
    version: int = Field(ge=1)
    version_sha: SHA256Hex
    source: str = Field(min_length=1)


class AgentDescriptor(FrozenStrictModel):
    agent_id: str = Field(min_length=1)
    fleet_index: int = Field(ge=1)
    display_name: str = Field(min_length=1)
    role: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    model_source: FieldSource
    stages: list[str] = Field(default_factory=list)
    runtime_binding: str = Field(min_length=1)
    principal: AgentPrincipal
    prompt: PromptBinding | None = None
    lifecycle: AgentLifecycle
    wired: bool
    definition_sha: SHA256Hex
    field_sources: dict[str, FieldSource] = Field(default_factory=dict)


class FleetSummary(FrozenStrictModel):
    mode: str = Field(min_length=1)
    agent_count: int = Field(ge=0)
    wired_count: int = Field(ge=0)
    principal_count: int = Field(ge=0)
    dedicated_service_accounts: int = Field(ge=0)
    by_model: dict[str, int] = Field(default_factory=dict)
    by_lifecycle: dict[str, int] = Field(default_factory=dict)
    by_stage: dict[str, int] = Field(default_factory=dict)
    registry_sha: SHA256Hex


class FleetRegistryResponse(StrictBaseModel):
    generated_at: TzAwareDatetime
    agents: list[AgentDescriptor] = Field(default_factory=list)
    principals: list[AgentPrincipal] = Field(default_factory=list)
    summary: FleetSummary


class CapabilityAuditRecord(FrozenStrictModel):
    recorded_at: TzAwareDatetime
    agent_id: str = Field(min_length=1)
    principal_id: str = Field(min_length=1)
    tool: str = Field(min_length=1)
    target: str = Field(min_length=1)
    capability: str = ""
    decision: str = Field(min_length=1)
    reasons: list[str] = Field(default_factory=list)
