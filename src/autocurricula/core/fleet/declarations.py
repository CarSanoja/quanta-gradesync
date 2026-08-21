from dataclasses import dataclass

from autocurricula.schemas.fleet import AgentLifecycle, Capability

PRINCIPAL_PREFIX = "agent://"

LLM_GENERATE = "llm.generate"
GCS_FETCH_BATCH = "gcs.fetch_batch"
FIRESTORE_CHECKPOINT = "firestore.checkpoint"
FIRESTORE_PROMPT_WRITE = "firestore.prompt_write"
SIS_WRITE_GRADES = "sis.write_grades"

TOOL_CAPABILITIES: dict[str, Capability] = {
    LLM_GENERATE: Capability.LLM_INVOKE,
    GCS_FETCH_BATCH: Capability.GCS_READ,
    FIRESTORE_CHECKPOINT: Capability.FIRESTORE_WRITE,
    FIRESTORE_PROMPT_WRITE: Capability.FIRESTORE_WRITE,
    SIS_WRITE_GRADES: Capability.SIS_WRITE,
}


@dataclass(frozen=True)
class AgentDeclaration:
    agent_id: str
    fleet_index: int
    display_name: str
    role: str
    stages: tuple[str, ...]
    capabilities: tuple[Capability, ...]
    lifecycle: AgentLifecycle = AgentLifecycle.ACTIVE
    model_setting: str | None = None
    container_attr: str | None = None
    prompt_variant_id: str | None = None

    @property
    def principal_id(self) -> str:
        return f"{PRINCIPAL_PREFIX}{self.agent_id}"


@dataclass(frozen=True)
class PrincipalDeclaration:
    principal_id: str
    description: str
    capabilities: tuple[Capability, ...]
    service_account_setting: str | None = None


INFRASTRUCTURE_PRINCIPALS: tuple[PrincipalDeclaration, ...] = (
    PrincipalDeclaration(
        principal_id="pipeline-orchestrator",
        description=(
            "Deterministic ADK stage graph: job records, checkpoints and stage "
            "state in Firestore"
        ),
        capabilities=(Capability.FIRESTORE_READ, Capability.FIRESTORE_WRITE),
    ),
    PrincipalDeclaration(
        principal_id="exam-fetcher",
        description="Stages exam batch objects from the upload bucket to local disk",
        capabilities=(Capability.GCS_READ,),
    ),
    PrincipalDeclaration(
        principal_id="sis-writer",
        description=(
            "Writes audited grade records to the school information system and the "
            "Firestore SIS ledger; the highest-risk external mutation in the fleet"
        ),
        capabilities=(Capability.SIS_WRITE, Capability.FIRESTORE_WRITE),
        service_account_setting="sis_writer_service_account",
    ),
)


def capability_for_tool(tool: str) -> Capability | None:
    return TOOL_CAPABILITIES.get(tool)
