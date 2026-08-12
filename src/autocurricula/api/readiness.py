import asyncio
from pathlib import Path

from autocurricula.config.clients import get_firestore_client
from autocurricula.config.settings import Settings

READINESS_PROBE_NAME = ".readiness-probe"
FIRESTORE_PING_TIMEOUT_SECONDS = 5.0


class BackendUnavailable(RuntimeError):
    pass


def settings_issues(settings: Settings) -> list[str]:
    if settings.local_mode:
        return []
    issues: list[str] = []
    if not settings.gcp_project_id:
        issues.append("gcp_project_id is required when local_mode is disabled")
    if not settings.pubsub_push_token:
        issues.append("pubsub_push_token is required when local_mode is disabled")
    if not settings.sis_base_url:
        issues.append("sis_base_url is required when local_mode is disabled")
    return issues


async def ping_backend(settings: Settings) -> str:
    if settings.local_mode:
        await asyncio.to_thread(_probe_local_filesystem, settings.local_data_dir)
        return "local"
    await asyncio.wait_for(
        asyncio.to_thread(_probe_firestore, settings),
        timeout=FIRESTORE_PING_TIMEOUT_SECONDS,
    )
    return "gcp"


def _probe_local_filesystem(data_dir: Path) -> None:
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        probe = data_dir / READINESS_PROBE_NAME
        probe.write_text("gradesync", encoding="utf-8")
        probe.unlink()
    except OSError as error:
        raise BackendUnavailable(f"local data directory is not writable: {error}") from error


def _probe_firestore(settings: Settings) -> None:
    try:
        client = get_firestore_client()
    except Exception as error:
        raise BackendUnavailable(f"firestore client unavailable: {error}") from error
    if client is None:
        raise BackendUnavailable("firestore client is not configured")
    try:
        list(
            client.collection(settings.firestore_checkpoints_collection)
            .limit(1)
            .stream()
        )
    except Exception as error:
        raise BackendUnavailable(f"firestore ping failed: {error}") from error
