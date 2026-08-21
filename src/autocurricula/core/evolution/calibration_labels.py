from collections.abc import Sequence
from typing import TYPE_CHECKING

from autocurricula.core.evolution.calibration_store import (
    CalibrationSample,
    CalibrationSet,
)
from autocurricula.schemas.grading import CriterionScore
from autocurricula.schemas.labels import Label

if TYPE_CHECKING:
    from autocurricula.core.review.label_store import LabelStore

LABEL_SAMPLE_SUMMARY = "Teacher-reviewed exam from the production review queue."
LABEL_SAMPLE_LIMIT = 200


def sample_from_label(label: Label) -> CalibrationSample | None:
    scored = [
        score
        for score in label.scores
        if score.human_score is not None and score.max_score
    ]
    if not scored:
        return None
    return CalibrationSample(
        submission_id=label.review_id,
        submission_summary=(
            f"{LABEL_SAMPLE_SUMMARY} decision={label.decision.value} "
            f"job={label.job_id} student={label.student_id}"
        ),
        criterion_ids=[score.criterion_id for score in scored],
        max_scores=[float(score.max_score) for score in scored],
        expected=[
            CriterionScore(
                criterion_id=score.criterion_id,
                score=float(score.human_score),
                comment=f"human {label.decision.value} decision on {label.review_id}",
                confidence=1.0,
            )
            for score in scored
        ],
    )


def samples_from_labels(labels: Sequence[Label]) -> list[CalibrationSample]:
    candidates = (sample_from_label(label) for label in labels)
    seen: dict[str, CalibrationSample] = {}
    for sample in candidates:
        if sample is not None:
            seen.setdefault(sample.submission_id, sample)
    return list(seen.values())


async def load_labelled_samples(
    store: "LabelStore",
    job_id: str | None = None,
    limit: int = LABEL_SAMPLE_LIMIT,
) -> list[CalibrationSample]:
    labels = await store.list_labels(job_id=job_id, limit=limit)
    return samples_from_labels(labels)


async def load_labelled_calibration_set(
    store: "LabelStore",
    job_id: str | None = None,
    limit: int = LABEL_SAMPLE_LIMIT,
) -> CalibrationSet:
    return CalibrationSet(await load_labelled_samples(store, job_id=job_id, limit=limit))
