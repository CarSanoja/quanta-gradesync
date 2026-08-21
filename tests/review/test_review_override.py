import pytest

from autocurricula.config.settings import Settings
from autocurricula.core.review import ReviewStateError
from autocurricula.core.review.override import OverrideValidationError
from autocurricula.schemas.labels import LabelDecision
from autocurricula.schemas.review import ReviewStatus
from tests.review.service_stack import CEILINGS, MACHINE, build_service, seed


async def test_override_writes_corrected_record_and_emits_label(
    settings: Settings,
) -> None:
    service, memory_manager = build_service(settings)
    await seed(service, "job-3:stu-3", "job-3")

    item = await service.override(
        "job-3:stu-3",
        {"crit-a": 4.0, "crit-b": 4.0},
        note="Legible work, the model misread the sign.",
        machine_scores=MACHINE,
        ceilings=CEILINGS,
    )

    assert item.status == ReviewStatus.OVERRIDDEN
    assert item.corrected_record is not None
    assert item.corrected_record.score == 8.0
    assert item.corrected_record.percentage == 80.0
    assert item.reviewer_note == "Legible work, the model misread the sign."
    profile = await memory_manager.persistent_store.get_profile("stu-3")
    assert profile is not None
    assert profile.terms[0].avg_percentage == 80.0
    labels = await service.label_store.list_labels()
    assert len(labels) == 1
    label = labels[0]
    assert label.decision == LabelDecision.OVERRIDE
    assert label.human_percentage == 80.0
    assert label.machine_percentage == 50.0
    assert {score.criterion_id: score.human_score for score in label.scores} == {
        "crit-a": 4.0,
        "crit-b": 4.0,
    }
    assert {score.criterion_id: score.max_score for score in label.scores} == CEILINGS
    assert label.reviewer_note == "Legible work, the model misread the sign."


async def test_override_rejects_scores_above_the_rubric_maximum(
    settings: Settings,
) -> None:
    service, memory_manager = build_service(settings)
    await seed(service, "job-4:stu-4", "job-4")

    with pytest.raises(OverrideValidationError, match="exceed their rubric maximum"):
        await service.override(
            "job-4:stu-4", {"crit-a": 4.5, "crit-b": 6.0}, ceilings=CEILINGS
        )

    item = await service.store.get("job-4:stu-4")
    assert item is not None
    assert item.status == ReviewStatus.PENDING
    assert await service.label_store.list_labels() == []


async def test_override_rejects_negative_and_unknown_criteria(
    settings: Settings,
) -> None:
    service, memory_manager = build_service(settings)
    await seed(service, "job-5:stu-5", "job-5")

    with pytest.raises(OverrideValidationError, match="must not be negative"):
        await service.override(
            "job-5:stu-5", {"crit-a": -1.0, "crit-b": 2.0}, ceilings=CEILINGS
        )
    with pytest.raises(OverrideValidationError, match="outside the rubric"):
        await service.override(
            "job-5:stu-5",
            {"crit-a": 1.0, "crit-b": 2.0, "crit-z": 1.0},
            ceilings=CEILINGS,
        )
    with pytest.raises(OverrideValidationError, match="missing"):
        await service.override("job-5:stu-5", {"crit-a": 1.0}, ceilings=CEILINGS)


async def test_override_falls_back_to_the_rubric_total_when_ceilings_are_unknown(
    settings: Settings,
) -> None:
    service, memory_manager = build_service(settings)
    await seed(service, "job-6:stu-6", "job-6")

    with pytest.raises(OverrideValidationError, match="rubric total"):
        await service.override("job-6:stu-6", {"crit-a": 11.0})

    item = await service.override("job-6:stu-6", {"crit-a": 9.0})
    assert item.corrected_record is not None
    assert item.corrected_record.percentage == 90.0


async def test_override_is_terminal(settings: Settings) -> None:
    service, memory_manager = build_service(settings)
    await seed(service, "job-7:stu-7", "job-7")

    await service.override(
        "job-7:stu-7", {"crit-a": 4.0, "crit-b": 4.0}, ceilings=CEILINGS
    )

    with pytest.raises(ReviewStateError):
        await service.approve("job-7:stu-7")
