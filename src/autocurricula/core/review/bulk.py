from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from pydantic import Field

from autocurricula.core.review.triage import is_batch_hold_only, judgement_reasons
from autocurricula.schemas.common import StrictBaseModel
from autocurricula.schemas.review import ReviewItem, ReviewStatus

JUDGEMENT_REFUSAL = (
    "this exam is held for a reason of its own and can only be decided one by one"
)
UNKNOWN_REFUSAL = "no exam is waiting under this id"
DECIDED_REFUSAL = "this exam was already decided as {status}"


class BulkReleaseRefusal(StrictBaseModel):
    review_id: str
    student_id: str | None = None
    reasons: list[str] = Field(default_factory=list)
    message: str


@dataclass(frozen=True)
class BulkReleaseSelection:
    releasable: list[ReviewItem] = field(default_factory=list)
    refused: list[BulkReleaseRefusal] = field(default_factory=list)
    excluded: list[BulkReleaseRefusal] = field(default_factory=list)
    already_released: list[str] = field(default_factory=list)


def judgement_refusal(item: ReviewItem) -> BulkReleaseRefusal:
    return BulkReleaseRefusal(
        review_id=item.review_id,
        student_id=item.student_id,
        reasons=judgement_reasons(item),
        message=JUDGEMENT_REFUSAL,
    )


def _decided_refusal(item: ReviewItem) -> BulkReleaseRefusal:
    return BulkReleaseRefusal(
        review_id=item.review_id,
        student_id=item.student_id,
        message=DECIDED_REFUSAL.format(status=item.status.value),
    )


def select_by_ids(
    found: Mapping[str, ReviewItem | None], requested: Sequence[str]
) -> BulkReleaseSelection:
    releasable: list[ReviewItem] = []
    refused: list[BulkReleaseRefusal] = []
    already: list[str] = []
    for review_id in requested:
        item = found.get(review_id)
        if item is None:
            refused.append(
                BulkReleaseRefusal(review_id=review_id, message=UNKNOWN_REFUSAL)
            )
            continue
        if item.status is ReviewStatus.APPROVED:
            already.append(item.review_id)
            continue
        if item.status is not ReviewStatus.PENDING:
            refused.append(_decided_refusal(item))
            continue
        if not is_batch_hold_only(item):
            refused.append(judgement_refusal(item))
            continue
        releasable.append(item)
    return BulkReleaseSelection(
        releasable=releasable, refused=refused, already_released=already
    )


def select_by_job(
    pending: Sequence[ReviewItem], job_id: str
) -> BulkReleaseSelection:
    releasable: list[ReviewItem] = []
    excluded: list[BulkReleaseRefusal] = []
    for item in pending:
        if item.job_id != job_id:
            continue
        if is_batch_hold_only(item):
            releasable.append(item)
        else:
            excluded.append(judgement_refusal(item))
    return BulkReleaseSelection(releasable=releasable, excluded=excluded)


__all__ = [
    "DECIDED_REFUSAL",
    "JUDGEMENT_REFUSAL",
    "UNKNOWN_REFUSAL",
    "BulkReleaseRefusal",
    "BulkReleaseSelection",
    "judgement_refusal",
    "select_by_ids",
    "select_by_job",
]
