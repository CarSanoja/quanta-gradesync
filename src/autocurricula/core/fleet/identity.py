from autocurricula.config.settings import Settings
from autocurricula.core.fleet.declarations import (
    INFRASTRUCTURE_PRINCIPALS,
    AgentDeclaration,
    PrincipalDeclaration,
)
from autocurricula.core.fleet.roster import AGENT_DECLARATIONS
from autocurricula.core.harness.capabilities import AgentGrant
from autocurricula.schemas.fleet import AgentPrincipal

LOCAL_SERVICE_ACCOUNT = "local:in-process"
AMBIENT_SERVICE_ACCOUNT = "ambient:cloud-run-runtime-identity"


def runtime_service_account(settings: Settings) -> str:
    if settings.local_mode:
        return LOCAL_SERVICE_ACCOUNT
    return settings.runtime_service_account or AMBIENT_SERVICE_ACCOUNT


def dedicated_service_account(
    settings: Settings, declaration: PrincipalDeclaration
) -> str:
    if declaration.service_account_setting is None or settings.local_mode:
        return ""
    value = getattr(settings, declaration.service_account_setting, "")
    return value if isinstance(value, str) else ""


def build_infrastructure_principal(
    settings: Settings, declaration: PrincipalDeclaration
) -> AgentPrincipal:
    dedicated = dedicated_service_account(settings, declaration)
    return AgentPrincipal(
        principal_id=declaration.principal_id,
        description=declaration.description,
        service_account=dedicated or runtime_service_account(settings),
        dedicated_service_account=bool(dedicated),
        impersonated=bool(dedicated) and settings.agent_impersonation_enabled,
        capabilities=list(declaration.capabilities),
    )


def build_agent_principal(
    settings: Settings, declaration: AgentDeclaration
) -> AgentPrincipal:
    return AgentPrincipal(
        principal_id=declaration.principal_id,
        description=f"In-process principal of the {declaration.display_name}",
        service_account=runtime_service_account(settings),
        dedicated_service_account=False,
        impersonated=False,
        capabilities=list(declaration.capabilities),
    )


def infrastructure_principals(settings: Settings) -> list[AgentPrincipal]:
    return [
        build_infrastructure_principal(settings, declaration)
        for declaration in INFRASTRUCTURE_PRINCIPALS
    ]


def agent_principals(settings: Settings) -> dict[str, AgentPrincipal]:
    return {
        declaration.agent_id: build_agent_principal(settings, declaration)
        for declaration in AGENT_DECLARATIONS
    }


def all_principals(settings: Settings) -> list[AgentPrincipal]:
    principals = list(agent_principals(settings).values())
    principals.extend(infrastructure_principals(settings))
    return sorted(principals, key=lambda principal: principal.principal_id)


def build_grants() -> list[AgentGrant]:
    grants = [
        AgentGrant(
            agent_id=declaration.agent_id,
            principal_id=declaration.principal_id,
            capabilities=frozenset(
                capability.value for capability in declaration.capabilities
            ),
        )
        for declaration in AGENT_DECLARATIONS
    ]
    grants.extend(
        AgentGrant(
            agent_id=declaration.principal_id,
            principal_id=declaration.principal_id,
            capabilities=frozenset(
                capability.value for capability in declaration.capabilities
            ),
        )
        for declaration in INFRASTRUCTURE_PRINCIPALS
    )
    return grants
