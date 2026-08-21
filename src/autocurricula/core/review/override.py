from collections.abc import Mapping

from autocurricula.schemas.review import ReviewItem
from autocurricula.schemas.sis_sync import SISGradeRecord

HUMAN_OVERRIDE_FEEDBACK = "Grade corrected by the teacher during human review."


class OverrideValidationError(Exception):
    pass


def derived_total_ceiling(item: ReviewItem) -> float | None:
    record = item.proposed_record
    if record.percentage <= 0:
        return None
    return 100.0 * record.score / record.percentage


def resolve_total_ceiling(
    item: ReviewItem, ceilings: Mapping[str, float] | None
) -> float:
    if ceilings:
        return sum(ceilings.values())
    derived = derived_total_ceiling(item)
    if derived is None or derived <= 0:
        raise OverrideValidationError(
            f"rubric maxima are unavailable for review item {item.review_id!r}; "
            "the corrected scores cannot be validated"
        )
    return derived


def validate_override_scores(
    item: ReviewItem,
    scores: Mapping[str, float],
    ceilings: Mapping[str, float] | None,
) -> float:
    if not scores:
        raise OverrideValidationError("an override must carry at least one score")
    total_ceiling = resolve_total_ceiling(item, ceilings)
    negatives = sorted(
        criterion_id for criterion_id, value in scores.items() if value < 0
    )
    if negatives:
        raise OverrideValidationError(
            f"corrected scores must not be negative: {negatives}"
        )
    if ceilings:
        _validate_against_rubric(scores, ceilings)
    else:
        above = sorted(
            criterion_id
            for criterion_id, value in scores.items()
            if value > total_ceiling
        )
        if above:
            raise OverrideValidationError(
                f"corrected scores exceed the rubric total {total_ceiling:g}: {above}"
            )
    total = sum(scores.values())
    if total > total_ceiling + 1e-9:
        raise OverrideValidationError(
            f"corrected total {total:g} exceeds the rubric maximum {total_ceiling:g}"
        )
    return total_ceiling


def _validate_against_rubric(
    scores: Mapping[str, float], ceilings: Mapping[str, float]
) -> None:
    unknown = sorted(set(scores) - set(ceilings))
    if unknown:
        raise OverrideValidationError(
            f"corrected scores reference criteria outside the rubric: {unknown}"
        )
    missing = sorted(set(ceilings) - set(scores))
    if missing:
        raise OverrideValidationError(
            f"an override must score every rubric criterion; missing: {missing}"
        )
    out_of_range = sorted(
        criterion_id
        for criterion_id, value in scores.items()
        if value > ceilings[criterion_id] + 1e-9
    )
    if out_of_range:
        raise OverrideValidationError(
            "corrected scores exceed their rubric maximum: "
            + ", ".join(
                f"{criterion_id}={scores[criterion_id]:g}>{ceilings[criterion_id]:g}"
                for criterion_id in out_of_range
            )
        )


def build_corrected_record(
    item: ReviewItem,
    scores: Mapping[str, float],
    total_ceiling: float,
    note: str | None = None,
) -> SISGradeRecord:
    total = sum(scores.values())
    percentage = min(100.0, max(0.0, 100.0 * total / total_ceiling))
    feedback = HUMAN_OVERRIDE_FEEDBACK if not note else f"{HUMAN_OVERRIDE_FEEDBACK} {note}"
    return item.proposed_record.model_copy(
        update={
            "score": round(total, 6),
            "percentage": round(percentage, 6),
            "feedback": feedback,
        }
    )
