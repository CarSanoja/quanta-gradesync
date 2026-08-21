from collections.abc import Iterable

from autocurricula.core.resilience.dead_letter_store import (
    DeadLetterEntry,
    DeadLetterStatus,
    DeadLetterStore,
)
from autocurricula.tools.sis_connector import SUCCESS_STATUSES

DLQ_KIND_SIS_WRITE = "sis_write"

REJECTED_REASON = "sis write returned non-success status"
UNREACHABLE_STATUS = "error:sis_unreachable"


def unreachable_reason(detail: str) -> str:
    return f"sis unreachable before any record-level verdict: {detail}"


def known_orphans(entries: Iterable[DeadLetterEntry]) -> dict[str, DeadLetterEntry]:
    return {entry.target: entry for entry in entries}


def _entry(
    job_id: str, target: str, reason: str, attempts: int, max_attempts: int
) -> DeadLetterEntry:
    return DeadLetterEntry(
        kind=DLQ_KIND_SIS_WRITE,
        job_id=job_id,
        target=target,
        reason=reason,
        attempts=attempts,
        max_attempts=max_attempts,
        status=(
            DeadLetterStatus.EXHAUSTED
            if attempts >= max_attempts
            else DeadLetterStatus.PENDING
        ),
    )


async def park_rejected(
    dead_letter: DeadLetterStore,
    job_id: str,
    targets: Iterable[str],
    known: dict[str, DeadLetterEntry],
    max_attempts: int,
) -> None:
    for target in targets:
        prior = known.get(target)
        attempts = (prior.attempts + 1) if prior is not None else 1
        await dead_letter.record(
            _entry(job_id, target, REJECTED_REASON, attempts, max_attempts)
        )


async def park_unreachable(
    dead_letter: DeadLetterStore,
    job_id: str,
    targets: Iterable[str],
    known: dict[str, DeadLetterEntry],
    max_attempts: int,
    detail: str,
) -> None:
    for target in targets:
        prior = known.get(target)
        attempts = prior.attempts if prior is not None else 0
        await dead_letter.record(
            _entry(job_id, target, unreachable_reason(detail), attempts, max_attempts)
        )


async def clear_written(
    dead_letter: DeadLetterStore,
    job_id: str,
    known: dict[str, DeadLetterEntry],
    statuses: dict[str, str],
) -> None:
    for target, entry in known.items():
        if entry.status != DeadLetterStatus.PENDING:
            continue
        if statuses.get(target) in SUCCESS_STATUSES:
            await dead_letter.resolve(job_id, DLQ_KIND_SIS_WRITE, target)
