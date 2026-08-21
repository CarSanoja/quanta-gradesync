from datetime import datetime, timezone

from autocurricula.core.evolution.calibration_labels import (
    load_labelled_samples,
    samples_from_labels,
)
from autocurricula.core.review.label_store import InMemoryLabelStore
from autocurricula.schemas.labels import Label, LabelDecision, LabelScore

CREATED_AT = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)


def make_label(
    review_id: str,
    decision: LabelDecision,
    scores: list[LabelScore],
    job_id: str = "job-1",
    human_percentage: float | None = 70.0,
) -> Label:
    return Label(
        label_id=f"{review_id}:{decision.value}",
        review_id=review_id,
        job_id=job_id,
        student_id=review_id.split(":")[-1],
        subject="matematicas",
        decision=decision,
        scores=scores,
        machine_percentage=50.0,
        human_percentage=human_percentage,
        created_at=CREATED_AT,
    )


def test_human_scores_become_calibration_ground_truth() -> None:
    label = make_label(
        "job-1:stu-1",
        LabelDecision.OVERRIDE,
        [
            LabelScore(
                criterion_id="crit-a", machine_score=2.0, human_score=3.5, max_score=4.0
            ),
            LabelScore(
                criterion_id="crit-b", machine_score=3.0, human_score=5.0, max_score=6.0
            ),
        ],
    )

    samples = samples_from_labels([label])

    assert len(samples) == 1
    sample = samples[0]
    assert sample.submission_id == "job-1:stu-1"
    assert sample.criterion_ids == ["crit-a", "crit-b"]
    assert sample.max_scores == [4.0, 6.0]
    assert sample.max_scores_by_criterion == {"crit-a": 4.0, "crit-b": 6.0}
    assert [score.score for score in sample.expected] == [3.5, 5.0]
    assert all(score.confidence == 1.0 for score in sample.expected)


def test_labels_without_a_human_score_or_ceiling_are_skipped() -> None:
    dismissed = make_label(
        "job-1:stu-2",
        LabelDecision.DISMISS,
        [LabelScore(criterion_id="crit-a", machine_score=2.0, max_score=4.0)],
        human_percentage=None,
    )
    ceiling_less = make_label(
        "job-1:stu-3",
        LabelDecision.OVERRIDE,
        [LabelScore(criterion_id="crit-a", machine_score=2.0, human_score=3.0)],
    )

    assert samples_from_labels([dismissed, ceiling_less]) == []


def test_partially_scored_labels_keep_only_usable_criteria() -> None:
    label = make_label(
        "job-1:stu-4",
        LabelDecision.APPROVE,
        [
            LabelScore(
                criterion_id="crit-a", machine_score=2.0, human_score=2.0, max_score=4.0
            ),
            LabelScore(criterion_id="crit-b", machine_score=3.0),
        ],
    )

    samples = samples_from_labels([label])

    assert len(samples) == 1
    assert samples[0].criterion_ids == ["crit-a"]


def test_duplicate_review_ids_collapse_to_one_sample() -> None:
    scores = [
        LabelScore(
            criterion_id="crit-a", machine_score=2.0, human_score=3.0, max_score=4.0
        )
    ]
    first = make_label("job-1:stu-5", LabelDecision.OVERRIDE, scores)
    second = make_label("job-1:stu-5", LabelDecision.APPROVE, scores)

    samples = samples_from_labels([first, second])

    assert [sample.submission_id for sample in samples] == ["job-1:stu-5"]


async def test_loader_reads_from_a_label_store() -> None:
    store = InMemoryLabelStore()
    await store.put(
        make_label(
            "job-1:stu-6",
            LabelDecision.OVERRIDE,
            [
                LabelScore(
                    criterion_id="crit-a",
                    machine_score=2.0,
                    human_score=3.0,
                    max_score=4.0,
                )
            ],
        )
    )
    await store.put(
        make_label(
            "job-2:stu-7",
            LabelDecision.OVERRIDE,
            [
                LabelScore(
                    criterion_id="crit-a",
                    machine_score=1.0,
                    human_score=2.0,
                    max_score=4.0,
                )
            ],
            job_id="job-2",
        )
    )

    everything = await load_labelled_samples(store)
    assert len(everything) == 2

    filtered = await load_labelled_samples(store, job_id="job-2")
    assert [sample.submission_id for sample in filtered] == ["job-2:stu-7"]
