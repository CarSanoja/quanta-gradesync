from autocurricula.config.settings import Settings
from autocurricula.schemas.labels import LabelDecision
from tests.review.service_stack import (
    CEILINGS,
    MACHINE,
    PROMPT_SHA,
    build_service,
    seed,
)


async def test_approve_emits_a_confirming_label(settings: Settings) -> None:
    service, memory_manager = build_service(settings)
    await seed(service, "job-1:stu-1", "job-1")

    await service.approve("job-1:stu-1", machine_scores=MACHINE, ceilings=CEILINGS)

    labels = await service.label_store.list_labels()
    assert len(labels) == 1
    label = labels[0]
    assert label.decision == LabelDecision.APPROVE
    assert label.student_id == "stu-1"
    assert label.human_percentage == 50.0
    assert label.machine_percentage == 50.0
    assert label.prompt_variant_id == "grading-v1"
    assert label.prompt_version_sha == PROMPT_SHA
    assert {score.criterion_id: score.human_score for score in label.scores} == MACHINE
    assert {score.criterion_id: score.machine_score for score in label.scores} == MACHINE


async def test_dismiss_emits_a_label_with_no_human_score(settings: Settings) -> None:
    service, memory_manager = build_service(settings)
    await seed(service, "job-2:stu-2", "job-2")

    await service.dismiss("job-2:stu-2", machine_scores=MACHINE, ceilings=CEILINGS)

    labels = await service.label_store.list_labels()
    assert len(labels) == 1
    label = labels[0]
    assert label.decision == LabelDecision.DISMISS
    assert label.human_percentage is None
    assert all(score.human_score is None for score in label.scores)
    assert {score.machine_score for score in label.scores} == set(MACHINE.values())


async def test_labels_are_filterable_by_job(settings: Settings) -> None:
    service, memory_manager = build_service(settings)
    await seed(service, "job-8:stu-8", "job-8")
    await seed(service, "job-9:stu-9", "job-9")

    await service.approve("job-8:stu-8", machine_scores=MACHINE, ceilings=CEILINGS)
    await service.dismiss("job-9:stu-9", machine_scores=MACHINE, ceilings=CEILINGS)

    assert len(await service.label_store.list_labels()) == 2
    only_job_8 = await service.label_store.list_labels(job_id="job-8")
    assert [label.review_id for label in only_job_8] == ["job-8:stu-8"]
    assert len(await service.label_store.list_labels(limit=1)) == 1
