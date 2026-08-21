from pathlib import Path

from autocurricula.api.review_context import load_review_context
from autocurricula.core.evolution.calibration_labels import load_labelled_samples
from autocurricula.core.memory.manager import MemoryManager
from autocurricula.core.orchestration.catalog import LocalJobCatalog
from autocurricula.core.orchestration.job_state import LocalCheckpointStore
from autocurricula.schemas.labels import LabelDecision
from autocurricula.schemas.review import ReviewStatus
from tests.review.flow_stack import (
    LOW_CONFIDENCE_STUDENT,
    build_stack,
    make_event,
    make_settings,
    stage_batch,
)

JOB_ID = "job-context-001"
REVIEW_ID = f"{JOB_ID}:{LOW_CONFIDENCE_STUDENT}"


async def run_job(tmp_path: Path):
    settings = make_settings(tmp_path)
    memory_manager = MemoryManager.from_settings(settings)
    runner, review_store, service = build_stack(settings, memory_manager)
    stage_batch(settings, JOB_ID)
    await runner.process(make_event(JOB_ID))
    checkpoint_store = LocalCheckpointStore(data_dir=settings.local_data_dir)
    catalog = LocalJobCatalog(staging_dir=settings.gcs_local_staging_dir)
    item = await review_store.get(REVIEW_ID)
    assert item is not None
    return settings, service, item, checkpoint_store, catalog


async def test_review_context_recovers_rubric_ceilings_and_machine_scores(
    tmp_path: Path,
) -> None:
    _, _, item, checkpoint_store, catalog = await run_job(tmp_path)

    context = await load_review_context(item, checkpoint_store, catalog)

    assert context.ceilings == {"crit-a": 4.0}
    assert context.machine_scores == {"crit-a": 2.0}


async def test_teacher_override_produces_a_usable_calibration_sample(
    tmp_path: Path,
) -> None:
    _, service, item, checkpoint_store, catalog = await run_job(tmp_path)
    context = await load_review_context(item, checkpoint_store, catalog)

    decided = await service.override(
        REVIEW_ID,
        {"crit-a": 3.5},
        note="partial credit for the correct method",
        machine_scores=context.machine_scores,
        ceilings=context.ceilings,
    )

    assert decided.status == ReviewStatus.OVERRIDDEN
    labels = await service.label_store.list_labels()
    assert [label.decision for label in labels] == [LabelDecision.OVERRIDE]
    assert labels[0].scores[0].max_score == 4.0
    assert labels[0].scores[0].machine_score == 2.0
    assert labels[0].scores[0].human_score == 3.5

    samples = await load_labelled_samples(service.label_store)
    assert len(samples) == 1
    sample = samples[0]
    assert sample.submission_id == REVIEW_ID
    assert sample.criterion_ids == ["crit-a"]
    assert sample.max_scores == [4.0]
    assert [score.score for score in sample.expected] == [3.5]


async def test_dismissed_items_do_not_pollute_the_calibration_pool(
    tmp_path: Path,
) -> None:
    _, service, item, checkpoint_store, catalog = await run_job(tmp_path)
    context = await load_review_context(item, checkpoint_store, catalog)

    await service.dismiss(
        REVIEW_ID,
        machine_scores=context.machine_scores,
        ceilings=context.ceilings,
    )

    labels = await service.label_store.list_labels()
    assert [label.decision for label in labels] == [LabelDecision.DISMISS]
    assert await load_labelled_samples(service.label_store) == []


async def test_approved_items_become_confirmed_calibration_samples(
    tmp_path: Path,
) -> None:
    _, service, item, checkpoint_store, catalog = await run_job(tmp_path)
    context = await load_review_context(item, checkpoint_store, catalog)

    await service.approve(
        REVIEW_ID,
        machine_scores=context.machine_scores,
        ceilings=context.ceilings,
    )

    samples = await load_labelled_samples(service.label_store)
    assert len(samples) == 1
    assert [score.score for score in samples[0].expected] == [2.0]
