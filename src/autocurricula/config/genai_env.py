import os

from autocurricula.config.settings import Settings

VERTEX_FLAG_VAR = "GOOGLE_GENAI_USE_VERTEXAI"
PROJECT_VAR = "GOOGLE_CLOUD_PROJECT"
LOCATION_VAR = "GOOGLE_CLOUD_LOCATION"


def configure_genai_env(settings: Settings) -> dict[str, str]:
    if settings.local_mode:
        return {}
    applied: dict[str, str] = {}
    for name, value in (
        (VERTEX_FLAG_VAR, "true"),
        (PROJECT_VAR, settings.gcp_project_id),
        (LOCATION_VAR, settings.gemini_location),
    ):
        if not value:
            continue
        os.environ.setdefault(name, value)
        applied[name] = os.environ[name]
    return applied
