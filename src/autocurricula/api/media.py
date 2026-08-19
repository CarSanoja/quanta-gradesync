from pathlib import Path

from autocurricula.config.settings import Settings
from autocurricula.tools.gcs_fetcher import FetchError, split_gcs_uri

GCS_SCHEME = "gs://"

MEDIA_TYPE_BY_SUFFIX = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".tiff": "image/tiff",
    ".heic": "image/heic",
    ".pdf": "application/pdf",
}


class DocumentAccessError(Exception):
    pass


class DocumentMissingError(Exception):
    pass


def allowed_roots(settings: Settings) -> list[Path]:
    roots: list[Path] = []
    for candidate in (settings.gcs_local_staging_dir, settings.local_data_dir):
        try:
            roots.append(Path(candidate).resolve())
        except OSError:
            continue
    return roots


def media_type_for(path: Path) -> str:
    media_type = MEDIA_TYPE_BY_SUFFIX.get(path.suffix.lower())
    if media_type is None:
        raise DocumentAccessError(f"unsupported document type {path.suffix!r}")
    return media_type


def _candidate_path(settings: Settings, reference: str) -> Path:
    if reference.startswith(GCS_SCHEME):
        bucket, blob_name = split_gcs_uri(reference)
        return Path(settings.gcs_local_staging_dir) / bucket / blob_name
    return Path(reference)


def resolve_document(settings: Settings, reference: str) -> Path:
    if not settings.local_mode:
        raise DocumentAccessError(
            "staged document serving is only available in local mode"
        )
    if not reference.strip():
        raise DocumentMissingError("document reference is empty")
    try:
        resolved = _candidate_path(settings, reference).resolve()
    except (FetchError, OSError, ValueError) as error:
        raise DocumentAccessError(f"document reference cannot be resolved: {error}") from error
    roots = allowed_roots(settings)
    if not any(resolved.is_relative_to(root) for root in roots):
        raise DocumentAccessError("document reference escapes the allowed data roots")
    media_type_for(resolved)
    if not resolved.is_file():
        raise DocumentMissingError(f"no staged document at {resolved}")
    return resolved
