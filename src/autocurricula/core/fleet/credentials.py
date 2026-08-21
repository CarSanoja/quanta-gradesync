import logging
from typing import Any

from autocurricula.config.settings import Settings
from autocurricula.core.fleet.declarations import INFRASTRUCTURE_PRINCIPALS

logger = logging.getLogger(__name__)

CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"
SIS_WRITER_PRINCIPAL = "sis-writer"


class ImpersonationUnavailable(RuntimeError):
    pass


def principal_service_account(settings: Settings, principal_id: str) -> str:
    if settings.local_mode:
        return ""
    for declaration in INFRASTRUCTURE_PRINCIPALS:
        if declaration.principal_id != principal_id:
            continue
        if declaration.service_account_setting is None:
            return ""
        value = getattr(settings, declaration.service_account_setting, "")
        return value if isinstance(value, str) else ""
    return ""


def impersonation_enabled(settings: Settings, principal_id: str) -> bool:
    return bool(
        settings.agent_impersonation_enabled
        and principal_service_account(settings, principal_id)
    )


def impersonated_credentials(settings: Settings, principal_id: str) -> Any:
    target = principal_service_account(settings, principal_id)
    if not target:
        raise ImpersonationUnavailable(
            f"principal {principal_id!r} has no dedicated service account configured"
        )
    from google.auth import default as application_default
    from google.auth import impersonated_credentials as impersonation

    source, _ = application_default(scopes=[CLOUD_PLATFORM_SCOPE])
    return impersonation.Credentials(
        source_credentials=source,
        target_principal=target,
        target_scopes=[CLOUD_PLATFORM_SCOPE],
        lifetime=settings.agent_impersonation_lifetime_seconds,
    )


def impersonated_id_token(settings: Settings, principal_id: str, audience: str) -> str:
    from google.auth import impersonated_credentials as impersonation
    from google.auth.transport.requests import Request

    delegate = impersonated_credentials(settings, principal_id)
    token_credentials = impersonation.IDTokenCredentials(
        delegate, target_audience=audience, include_email=True
    )
    token_credentials.refresh(Request())
    if not token_credentials.token:
        raise ImpersonationUnavailable(
            f"IAM Service Account Credentials returned no id token for {principal_id!r}"
        )
    return token_credentials.token


def sis_writer_authorization(settings: Settings, fallback_token: str) -> str:
    if not impersonation_enabled(settings, SIS_WRITER_PRINCIPAL):
        return f"Bearer {fallback_token}"
    audience = settings.sis_audience or settings.sis_base_url
    try:
        return f"Bearer {impersonated_id_token(settings, SIS_WRITER_PRINCIPAL, audience)}"
    except Exception as error:
        logger.warning(
            "sis-writer impersonation failed, falling back to the ambient identity: %s",
            error,
        )
        return f"Bearer {fallback_token}"


def sis_writer_firestore_client(settings: Settings) -> Any | None:
    if not impersonation_enabled(settings, SIS_WRITER_PRINCIPAL):
        return None
    try:
        from google.cloud import firestore

        return firestore.Client(
            project=settings.gcp_project_id,
            credentials=impersonated_credentials(settings, SIS_WRITER_PRINCIPAL),
        )
    except Exception as error:
        logger.warning(
            "sis-writer impersonated firestore client unavailable, falling back to "
            "the ambient runtime identity: %s",
            error,
        )
        return None
