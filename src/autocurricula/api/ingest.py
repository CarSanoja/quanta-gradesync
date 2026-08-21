import re
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import JSONResponse

from autocurricula.api.dependencies import AppContainer, get_container
from autocurricula.api.ingest_storage import (
    IngestCollision,
    IngestUnavailable,
    build_ingest_storage,
    copy_sample_batch,
    upload_object_name,
)
from autocurricula.api.webhooks import require_push_token
from autocurricula.core.orchestration.manifest_inference import (
    LOT_CODE_PATTERN,
    LOT_CONVENTION,
    MIME_BY_EXTENSION,
)


async def require_ingest_token(
    request: Request, container: AppContainer = Depends(get_container)
) -> None:
    require_push_token(request, container.settings.pubsub_push_token)


ingest_router = APIRouter(tags=["ingest"], dependencies=[Depends(require_ingest_token)])

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_BATCH_OBJECTS = 200

MODE_NEW = "new"
MODE_REPLACE = "replace"
MODE_RENAME = "rename"
UPLOAD_MODES = frozenset({MODE_NEW, MODE_REPLACE, MODE_RENAME})

STUDENT_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _unprocessable(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=detail
    )


def validate_lot_code(lot_code: str) -> str:
    stripped = lot_code.strip()
    if LOT_CODE_PATTERN.fullmatch(stripped) is None:
        raise _unprocessable(
            f"lot code {stripped!r} does not follow convention {LOT_CONVENTION}"
        )
    return stripped


def validate_file_name(raw_name: str, stem_is_student_id: bool = True) -> tuple[str, str, str]:
    name = Path(raw_name.replace("\\", "/")).name.strip()
    if not name or name.startswith("."):
        raise _unprocessable("upload needs a plain file name; the stem is the student id")
    suffix = Path(name).suffix.lower()
    if suffix not in MIME_BY_EXTENSION:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"extension {suffix!r} is not gradable; allowed: "
                f"{', '.join(sorted(MIME_BY_EXTENSION))}"
            ),
        )
    stem = Path(name).stem
    if stem_is_student_id and not STUDENT_NAME_PATTERN.fullmatch(stem):
        raise _unprocessable(
            f"file stem {stem!r} is not a valid student id "
            "(letters, digits, dot, dash, underscore)"
        )
    return name, stem, suffix


def resolve_target_name(mode: str, name: str, suffix: str, new_student_name: str) -> str:
    if mode != MODE_RENAME:
        return name
    candidate = new_student_name.strip()
    if not candidate or STUDENT_NAME_PATTERN.fullmatch(candidate) is None:
        raise _unprocessable(
            "mode=rename requires a new_student_name of letters, digits, dot, "
            "dash or underscore"
        )
    return f"{candidate}{suffix}"


def collision_response(object_name: str, lot_code: str, student_id: str) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={
            "collision": True,
            "object": object_name,
            "lot_code": lot_code,
            "student_id": student_id,
            "detail": (
                f"a scan for student {student_id!r} already exists in this batch; "
                "replace it or upload under a different student name"
            ),
        },
    )


@ingest_router.post("/ingest/exam")
async def ingest_exam(
    file: UploadFile = File(...),
    lot_code: str = Form(...),
    mode: str = Form(default=MODE_NEW),
    new_student_name: str = Form(default=""),
    container: AppContainer = Depends(get_container),
):
    if mode not in UPLOAD_MODES:
        raise _unprocessable(f"mode must be one of {sorted(UPLOAD_MODES)}")
    lot = validate_lot_code(lot_code)
    name, stem, suffix = validate_file_name(file.filename or "", mode != MODE_RENAME)
    target_name = resolve_target_name(mode, name, suffix, new_student_name)
    student_id = Path(target_name).stem
    payload = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(payload) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"upload exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit",
        )
    if not payload:
        raise _unprocessable("uploaded file is empty")
    try:
        storage = build_ingest_storage(container.settings)
    except IngestUnavailable as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)
        ) from error
    object_name = upload_object_name(lot, target_name)
    prefix = f"{upload_object_name(lot, '')}"
    if mode != MODE_REPLACE and await storage.count_objects(prefix) >= MAX_BATCH_OBJECTS:
        raise _unprocessable(
            f"batch {lot!r} already holds {MAX_BATCH_OBJECTS} objects; "
            "start a new lot instead"
        )
    try:
        bucket = await storage.store(
            object_name,
            payload,
            MIME_BY_EXTENSION[suffix],
            overwrite=(mode == MODE_REPLACE),
        )
    except IngestCollision:
        return collision_response(object_name, lot, student_id)
    return {
        "status": "stored",
        "mode": mode,
        "bucket": bucket,
        "object": object_name,
        "lot_code": lot,
        "student_id": student_id,
        "size_bytes": len(payload),
    }


@ingest_router.post("/ingest/sample-batch")
async def ingest_sample_batch(
    container: AppContainer = Depends(get_container),
):
    if container.settings.local_mode:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="sample batch copy needs gcp mode; the demo objects live in gcs",
        )
    try:
        return await copy_sample_batch(container.settings)
    except IngestUnavailable as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)
        ) from error
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"sample batch copy failed: {error}",
        ) from error
