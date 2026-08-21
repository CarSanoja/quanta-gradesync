from collections.abc import Sequence

from pydantic import Field

from autocurricula.api.teacher_batch import TeacherBatchProgress
from autocurricula.api.teacher_views import TeacherReviewView
from autocurricula.core.review.triage import GROUP_BATCH_HOLD, GROUP_JUDGEMENT
from autocurricula.schemas.common import StrictBaseModel

JUDGEMENT_TITLE = "Needs your judgement"
BATCH_HOLD_TITLE = "Held only by the batch rule"

JUDGEMENT_NOTE = (
    "Each of these was held for a reason of its own. You see the page, the line the "
    "grader quoted and the grade it proposes — one exam at a time."
)
JUDGEMENT_EMPTY = "Nothing here needs your judgement. Every held exam is a batch hold."
BATCH_HOLD_NOTE = (
    "Nothing is wrong with these individually. The whole batch was held as a "
    "precaution, so they are all waiting on one decision from you."
)
BATCH_HOLD_EMPTY = "No exam is waiting on the batch rule."


class TeacherReasonCount(StrictBaseModel):
    key: str
    label: str
    count: int = Field(ge=0)


class TeacherTriageGroup(StrictBaseModel):
    key: str
    title: str
    count: int = Field(ge=0)
    note: str
    empty_note: str
    bulk_releasable: bool
    reasons: list[TeacherReasonCount] = Field(default_factory=list)
    items: list[TeacherReviewView] = Field(default_factory=list)


class TeacherSummary(StrictBaseModel):
    waiting: list[TeacherReviewView] = Field(default_factory=list)
    waiting_count: int = Field(ge=0)
    judgement: TeacherTriageGroup
    batch_hold: TeacherTriageGroup
    batch: TeacherBatchProgress | None = None


def reason_breakdown(items: Sequence[TeacherReviewView]) -> list[TeacherReasonCount]:
    counts: dict[str, TeacherReasonCount] = {}
    for item in items:
        current = counts.get(item.reason_key)
        if current is None:
            counts[item.reason_key] = TeacherReasonCount(
                key=item.reason_key, label=item.primary_reason, count=1
            )
            continue
        counts[item.reason_key] = current.model_copy(
            update={"count": current.count + 1}
        )
    return sorted(counts.values(), key=lambda entry: (-entry.count, entry.key))


def _group(
    key: str,
    title: str,
    note: str,
    empty_note: str,
    bulk_releasable: bool,
    items: Sequence[TeacherReviewView],
) -> TeacherTriageGroup:
    return TeacherTriageGroup(
        key=key,
        title=title,
        count=len(items),
        note=note,
        empty_note=empty_note,
        bulk_releasable=bulk_releasable,
        reasons=reason_breakdown(items),
        items=list(items),
    )


def build_summary(
    views: Sequence[TeacherReviewView], batch: TeacherBatchProgress | None
) -> TeacherSummary:
    judgement = [view for view in views if view.group == GROUP_JUDGEMENT]
    batch_hold = [view for view in views if view.group == GROUP_BATCH_HOLD]
    return TeacherSummary(
        waiting=list(views),
        waiting_count=len(views),
        judgement=_group(
            GROUP_JUDGEMENT,
            JUDGEMENT_TITLE,
            JUDGEMENT_NOTE,
            JUDGEMENT_EMPTY,
            False,
            judgement,
        ),
        batch_hold=_group(
            GROUP_BATCH_HOLD,
            BATCH_HOLD_TITLE,
            BATCH_HOLD_NOTE,
            BATCH_HOLD_EMPTY,
            True,
            batch_hold,
        ),
        batch=batch,
    )


__all__ = [
    "BATCH_HOLD_EMPTY",
    "BATCH_HOLD_NOTE",
    "BATCH_HOLD_TITLE",
    "JUDGEMENT_EMPTY",
    "JUDGEMENT_NOTE",
    "JUDGEMENT_TITLE",
    "TeacherReasonCount",
    "TeacherSummary",
    "TeacherTriageGroup",
    "build_summary",
    "reason_breakdown",
]
