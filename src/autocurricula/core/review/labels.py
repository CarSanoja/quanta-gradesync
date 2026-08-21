from collections.abc import Mapping

from autocurricula.schemas.common import utc_now
from autocurricula.schemas.labels import (
    Label,
    LabelDecision,
    LabelScore,
    build_label_id,
)
from autocurricula.schemas.review import ReviewItem


def _label_scores(
    machine_scores: Mapping[str, float] | None,
    human_scores: Mapping[str, float] | None,
    ceilings: Mapping[str, float] | None,
) -> list[LabelScore]:
    machine = dict(machine_scores or {})
    human = dict(human_scores or {})
    maxima = dict(ceilings or {})
    criterion_ids = sorted(set(machine) | set(human))
    return [
        LabelScore(
            criterion_id=criterion_id,
            machine_score=machine.get(criterion_id),
            human_score=human.get(criterion_id),
            max_score=maxima.get(criterion_id),
        )
        for criterion_id in criterion_ids
    ]


def build_label(
    item: ReviewItem,
    decision: LabelDecision,
    *,
    machine_scores: Mapping[str, float] | None = None,
    human_scores: Mapping[str, float] | None = None,
    ceilings: Mapping[str, float] | None = None,
    human_percentage: float | None = None,
    note: str | None = None,
) -> Label:
    provenance = item.proposed_record.provenance
    return Label(
        label_id=build_label_id(item.review_id, decision),
        review_id=item.review_id,
        job_id=item.job_id,
        student_id=item.student_id,
        subject=item.subject,
        decision=decision,
        scores=_label_scores(machine_scores, human_scores, ceilings),
        machine_percentage=item.proposed_record.percentage,
        human_percentage=human_percentage,
        prompt_variant_id=provenance.prompt_variant_id if provenance else None,
        prompt_version_sha=provenance.prompt_version_sha if provenance else None,
        reviewer_note=note,
        created_at=utc_now(),
    )


def confirmation_label(
    item: ReviewItem,
    *,
    machine_scores: Mapping[str, float] | None = None,
    ceilings: Mapping[str, float] | None = None,
) -> Label:
    return build_label(
        item,
        LabelDecision.APPROVE,
        machine_scores=machine_scores,
        human_scores=machine_scores,
        ceilings=ceilings,
        human_percentage=item.proposed_record.percentage,
    )


def rejection_label(
    item: ReviewItem,
    *,
    machine_scores: Mapping[str, float] | None = None,
    ceilings: Mapping[str, float] | None = None,
) -> Label:
    return build_label(
        item,
        LabelDecision.DISMISS,
        machine_scores=machine_scores,
        ceilings=ceilings,
    )


def correction_label(
    item: ReviewItem,
    human_scores: Mapping[str, float],
    human_percentage: float,
    *,
    machine_scores: Mapping[str, float] | None = None,
    ceilings: Mapping[str, float] | None = None,
    note: str | None = None,
) -> Label:
    return build_label(
        item,
        LabelDecision.OVERRIDE,
        machine_scores=machine_scores,
        human_scores=human_scores,
        ceilings=ceilings,
        human_percentage=human_percentage,
        note=note,
    )
