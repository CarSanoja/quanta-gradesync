import asyncio
import logging
import re
from pathlib import Path
from typing import Protocol, runtime_checkable

from pydantic import Field

from autocurricula.config import Settings
from autocurricula.core.armor import safe_identifier, scan_identifier
from autocurricula.core.orchestration.catalog import (
    BatchManifest,
    CatalogError,
    JobCatalog,
    align_manifest,
)
from autocurricula.core.orchestration.catalog_defaults import (
    CatalogDefaults,
    normalize_token,
    parse_defaults,
)
from autocurricula.schemas.common import StrictBaseModel
from autocurricula.schemas.events import PubSubJobEvent
from autocurricula.schemas.exam import ExamBatch, ExamFile, ExamSubmission

logger = logging.getLogger(__name__)

LOT_CODE_PATTERN = re.compile(
    r"^(?P<year>\d{4})_(?P<subject>[A-Za-z0-9\-]+)_(?P<class_id>[A-Za-z0-9\-]+)"
    r"_(?P<assessment>[A-Za-z0-9\-]+)$"
)
LOT_CONVENTION = "{year}_{subject}_{class_id}_{assessment}"
DEFAULTS_NAME = "catalog-defaults.json"
MIME_BY_EXTENSION = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".pdf": "application/pdf",
    ".heic": "image/heic",
}


class LotCode(StrictBaseModel):
    year: int = Field(ge=2000, le=2100)
    subject: str = Field(min_length=1)
    class_id: str = Field(min_length=1)
    assessment: str = Field(min_length=1)


def parse_lot_code(prefix: str) -> LotCode:
    segment = [part for part in prefix.split("/") if part.strip()]
    if not segment:
        raise CatalogError("batch prefix is empty; cannot infer lot code")
    code = segment[-1].strip()
    match = LOT_CODE_PATTERN.fullmatch(code)
    if match is None:
        raise CatalogError(
            f"lot code {segment[-1]!r} does not follow convention {LOT_CONVENTION}"
        )
    hit = scan_identifier(code)
    if hit is not None:
        raise CatalogError(
            f"lot code {code!r} reads as an instruction to the grading system "
            f"({hit.technique} match on {hit.quote!r}); rename the batch folder"
        )
    return LotCode(
        year=int(match.group("year")),
        subject=match.group("subject"),
        class_id=match.group("class_id"),
        assessment=match.group("assessment"),
    )


def ensure_lot_matches_event(lot: LotCode, event: PubSubJobEvent) -> None:
    if normalize_token(lot.subject) != normalize_token(event.subject):
        raise CatalogError(
            f"lot code subject {lot.subject!r} does not match event subject {event.subject!r}"
        )
    if normalize_token(lot.class_id) != normalize_token(event.class_id):
        raise CatalogError(
            f"lot code class {lot.class_id!r} does not match event class {event.class_id!r}"
        )


def build_submissions(event: PubSubJobEvent, file_names: list[str]) -> list[ExamSubmission]:
    prefix = event.exam_batch_prefix.rstrip("/")
    submissions: list[ExamSubmission] = []
    for name in sorted(file_names):
        mime = MIME_BY_EXTENSION.get(Path(name).suffix.lower())
        if mime is None:
            continue
        stem = Path(name).stem
        identity = safe_identifier(stem)
        if identity != stem:
            logger.warning(
                "file name %r is not usable as a student id; grading it as %r",
                name,
                identity,
            )
        submissions.append(
            ExamSubmission(
                submission_id=identity,
                student_id=identity,
                files=[
                    ExamFile(
                        gcs_uri=f"gs://{event.bucket}/{prefix}/{name}",
                        mime_type=mime,
                        page_count=1,
                    )
                ],
            )
        )
    if not submissions:
        raise CatalogError(f"no gradable files found under gs://{event.bucket}/{prefix}")
    return submissions


def assemble_manifest(
    event: PubSubJobEvent,
    binding: CatalogDefaults.SubjectBinding,
    file_names: list[str],
) -> BatchManifest:
    manifest = BatchManifest(
        batch=ExamBatch(
            job_id=event.job_id,
            class_id=event.class_id,
            subject=event.subject,
            grade_level=binding.grade_level,
            rubric_id=binding.rubric.rubric_id,
            submissions=build_submissions(event, file_names),
        ),
        rubric=binding.rubric,
        curriculum_standard=binding.curriculum_standard,
    )
    return align_manifest(event, manifest)


@runtime_checkable
class ManifestInferer(Protocol):
    async def infer_manifest(self, event: PubSubJobEvent) -> BatchManifest: ...


class LocalManifestInferer:
    def __init__(self, staging_dir: Path) -> None:
        self._staging_dir = Path(staging_dir)

    async def infer_manifest(self, event: PubSubJobEvent) -> BatchManifest:
        lot = parse_lot_code(event.exam_batch_prefix)
        ensure_lot_matches_event(lot, event)
        defaults = await self._load_defaults(event)
        binding = defaults.binding_for(event.subject)
        names = await asyncio.to_thread(self._list_file_names, event)
        return assemble_manifest(event, binding, names)

    async def _load_defaults(self, event: PubSubJobEvent) -> CatalogDefaults:
        path = self._staging_dir / event.bucket / DEFAULTS_NAME
        if not await asyncio.to_thread(path.is_file):
            raise CatalogError(f"catalog defaults not found at {path}")
        return parse_defaults(await asyncio.to_thread(path.read_bytes))

    def _list_file_names(self, event: PubSubJobEvent) -> list[str]:
        root = self._staging_dir / event.bucket / event.exam_batch_prefix.rstrip("/")
        if not root.is_dir():
            raise CatalogError(f"no staged batch directory at {root}")
        return [path.name for path in root.iterdir() if path.is_file()]


class FallbackJobCatalog:
    def __init__(self, primary: JobCatalog, inferer: ManifestInferer) -> None:
        self._primary = primary
        self._inferer = inferer

    async def load_manifest(self, event: PubSubJobEvent) -> BatchManifest:
        from autocurricula.core.orchestration.catalog import ManifestNotFound

        try:
            return await self._primary.load_manifest(event)
        except ManifestNotFound:
            return await self._inferer.infer_manifest(event)


def build_manifest_inferer(settings: Settings) -> ManifestInferer:
    if settings.local_mode:
        return LocalManifestInferer(staging_dir=settings.gcs_local_staging_dir)
    from autocurricula.core.orchestration.manifest_inference_gcs import (
        GcsManifestInferer,
    )

    return GcsManifestInferer(settings=settings)
