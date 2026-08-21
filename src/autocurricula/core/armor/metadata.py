import hashlib
from typing import Any

from autocurricula.core.armor.deterministic import scan_identifier
from autocurricula.core.armor.encoding import has_confusables
from autocurricula.schemas.armor import ArmorSeverity, ArmorVerdict
from autocurricula.schemas.exam import ExamSubmission

CHANNEL_SUBMISSION_ID = "submission id"
CHANNEL_STUDENT_ID = "student id"
CHANNEL_OBJECT_PATH = "object path"
CHANNEL_LOCAL_PATH = "staged file path"

MAX_IDENTIFIER_CHARS = 96
MAX_EXTENSION_CHARS = 5
QUOTE_LIMIT = 120
REDACTED_PREFIX = "redacted"
REDACTED_DIGEST_CHARS = 10


def manifest_strings(submission: ExamSubmission) -> list[tuple[str, str]]:
    values = [
        (CHANNEL_SUBMISSION_ID, submission.submission_id),
        (CHANNEL_STUDENT_ID, submission.student_id),
    ]
    for exam_file in submission.files:
        values.append((CHANNEL_OBJECT_PATH, exam_file.gcs_uri))
        if exam_file.local_path is not None:
            values.append((CHANNEL_LOCAL_PATH, exam_file.local_path))
    return values


def screen_metadata(submission: ExamSubmission) -> ArmorVerdict | None:
    for channel, value in manifest_strings(submission):
        hit = scan_identifier(value)
        if hit is None:
            continue
        return ArmorVerdict(
            injection_detected=True,
            quoted_text=value[:QUOTE_LIMIT],
            severity=ArmorSeverity.HIGH,
            rationale=(
                f"the {channel} carries text addressed to the grading system "
                f"({hit.technique} match on {hit.pattern!r}): {hit.quote}"
            ),
        )
    return None


def redacted_token(value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return f"{REDACTED_PREFIX}-{digest[:REDACTED_DIGEST_CHARS]}"


def is_safe_identifier(value: str) -> bool:
    if len(value) > MAX_IDENTIFIER_CHARS or has_confusables(value):
        return False
    return scan_identifier(value) is None


def safe_identifier(value: str) -> str:
    if not value:
        return value
    return value if is_safe_identifier(value) else redacted_token(value)


def _safe_segment(segment: str) -> str:
    stem, dot, extension = segment.rpartition(".")
    if dot and stem and extension.isalnum() and len(extension) <= MAX_EXTENSION_CHARS:
        return f"{safe_identifier(stem)}.{extension}"
    return safe_identifier(segment)


def safe_path(value: str) -> str:
    scheme, separator, remainder = value.partition("://")
    prefix = f"{scheme}{separator}" if separator else ""
    body = remainder if separator else value
    segments = [
        segment if segment in ("", ".", "..") else _safe_segment(segment)
        for segment in body.split("/")
    ]
    return prefix + "/".join(segments)


def prompt_safe_submission(submission: ExamSubmission) -> dict[str, Any]:
    payload = submission.model_dump(mode="json")
    payload["submission_id"] = safe_identifier(submission.submission_id)
    payload["student_id"] = safe_identifier(submission.student_id)
    for entry, exam_file in zip(payload["files"], submission.files, strict=True):
        entry["gcs_uri"] = safe_path(exam_file.gcs_uri)
        if exam_file.local_path is not None:
            entry["local_path"] = safe_path(exam_file.local_path)
    return payload
