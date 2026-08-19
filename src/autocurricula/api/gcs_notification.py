import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from autocurricula.core.orchestration.catalog import MANIFEST_NAME, CatalogError
from autocurricula.core.orchestration.manifest_inference import (
    LOT_CODE_PATTERN,
    LOT_CONVENTION,
    MIME_BY_EXTENSION,
    parse_lot_code,
)
from autocurricula.schemas.common import utc_now
from autocurricula.schemas.events import (
    PubSubEnvelope,
    PubSubJobEvent,
    decode_message_payload,
)

BATCHES_SEGMENT = "batches"
FINALIZE_EVENT_TYPE = "OBJECT_FINALIZE"
GRADABLE_SUFFIXES = frozenset(MIME_BY_EXTENSION)
NON_SLUG_CHARS = re.compile(r"[^a-z0-9]+")
FALLBACK_JOB_ID = "exam-batch"


class IgnoredObject(Exception):
    pass


@dataclass(frozen=True)
class BatchObject:
    prefix: str
    lot_code: str
    file_name: str


@dataclass(frozen=True)
class PushResolution:
    event: PubSubJobEvent | None = None
    from_notification: bool = False
    ignored_reason: str | None = None


def derive_job_id(batch_prefix: str) -> str:
    segments = [
        segment
        for segment in batch_prefix.split("/")
        if segment.strip() and segment != BATCHES_SEGMENT
    ]
    slug = NON_SLUG_CHARS.sub("-", "-".join(segments).lower()).strip("-")
    return slug or FALLBACK_JOB_ID


def looks_like_notification(
    envelope: PubSubEnvelope, payload: dict[str, Any]
) -> bool:
    if "job_id" in payload:
        return False
    attributes = envelope.message.attributes
    if "eventType" in attributes or "objectId" in attributes:
        return True
    return "bucket" in payload and "name" in payload


def locate_batch_object(object_name: str) -> BatchObject:
    if not object_name or object_name.endswith("/"):
        raise IgnoredObject(f"object {object_name!r} is a folder placeholder")
    segments = object_name.split("/")
    if BATCHES_SEGMENT not in segments:
        raise IgnoredObject(
            f"object {object_name!r} is not under a {BATCHES_SEGMENT}/<lot>/ prefix"
        )
    index = len(segments) - 1 - segments[::-1].index(BATCHES_SEGMENT)
    if len(segments) != index + 3:
        raise IgnoredObject(
            f"object {object_name!r} is not a direct child of a batch prefix"
        )
    lot_code = segments[index + 1]
    if LOT_CODE_PATTERN.fullmatch(lot_code) is None:
        raise IgnoredObject(
            f"lot code {lot_code!r} does not follow convention {LOT_CONVENTION}"
        )
    file_name = segments[index + 2]
    if file_name != MANIFEST_NAME and Path(file_name).suffix.lower() not in GRADABLE_SUFFIXES:
        raise IgnoredObject(f"file {file_name!r} is not a gradable exam file")
    return BatchObject(
        prefix="/".join(segments[: index + 2]),
        lot_code=lot_code,
        file_name=file_name,
    )


def translate_notification(
    envelope: PubSubEnvelope, payload: dict[str, Any]
) -> PubSubJobEvent:
    attributes = envelope.message.attributes
    event_type = attributes.get("eventType") or FINALIZE_EVENT_TYPE
    if event_type != FINALIZE_EVENT_TYPE:
        raise IgnoredObject(f"event type {event_type!r} does not create exam batches")
    bucket = str(payload.get("bucket") or attributes.get("bucketId") or "").strip()
    if not bucket:
        raise IgnoredObject("notification carries no bucket")
    object_name = str(payload.get("name") or attributes.get("objectId") or "").strip()
    located = locate_batch_object(object_name)
    try:
        lot = parse_lot_code(located.prefix)
    except CatalogError as error:
        raise IgnoredObject(str(error)) from error
    return PubSubJobEvent(
        job_id=derive_job_id(located.prefix),
        bucket=bucket,
        exam_batch_prefix=located.prefix,
        class_id=lot.class_id,
        subject=lot.subject,
        triggered_at=utc_now(),
    )


def resolve_push_event(body: dict[str, Any]) -> PushResolution:
    envelope = PubSubEnvelope.model_validate(body)
    payload = decode_message_payload(envelope)
    if not looks_like_notification(envelope, payload):
        return PushResolution(event=PubSubJobEvent.model_validate(payload))
    try:
        event = translate_notification(envelope, payload)
    except IgnoredObject as error:
        return PushResolution(ignored_reason=str(error))
    return PushResolution(event=event, from_notification=True)
