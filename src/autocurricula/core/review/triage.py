from collections.abc import Iterable

from autocurricula.schemas.review import ReviewItem, ReviewKind

BATCH_ANOMALY_MARKER = "batch anomaly"
GROUP_JUDGEMENT = "judgement"
GROUP_BATCH_HOLD = "batch_hold"


def is_batch_anomaly_reason(reason: str) -> bool:
    return BATCH_ANOMALY_MARKER in reason.lower()


def judgement_reasons(item: ReviewItem) -> list[str]:
    if item.kind is not ReviewKind.GRADE:
        return list(item.reasons)
    return [reason for reason in item.reasons if not is_batch_anomaly_reason(reason)]


def is_batch_hold_only(item: ReviewItem) -> bool:
    if item.kind is not ReviewKind.GRADE:
        return False
    if judgement_reasons(item):
        return False
    return any(is_batch_anomaly_reason(reason) for reason in item.reasons)


def triage_group(item: ReviewItem) -> str:
    return GROUP_BATCH_HOLD if is_batch_hold_only(item) else GROUP_JUDGEMENT


def split_by_group(
    items: Iterable[ReviewItem],
) -> tuple[list[ReviewItem], list[ReviewItem]]:
    judgement: list[ReviewItem] = []
    batch_hold: list[ReviewItem] = []
    for item in items:
        target = batch_hold if is_batch_hold_only(item) else judgement
        target.append(item)
    return judgement, batch_hold


__all__ = [
    "BATCH_ANOMALY_MARKER",
    "GROUP_BATCH_HOLD",
    "GROUP_JUDGEMENT",
    "is_batch_anomaly_reason",
    "is_batch_hold_only",
    "judgement_reasons",
    "split_by_group",
    "triage_group",
]
