from pathlib import Path

from autocurricula.api.teacher_views import LATE_SCAN, translate_reasons
from autocurricula.core.memory.manager import MemoryManager
from autocurricula.core.orchestration.batch_listing import (
    LocalBatchLister,
    compare_batch_objects,
)
from autocurricula.core.orchestration.goal_checks import CHECK_BATCH_FILES_COMPLETE
from autocurricula.core.orchestration.job_state import JobStage
from autocurricula.schemas.review import ReviewKind
from tests.orchestration.incident_fixtures import (
    CrashingEvaluator,
    build_incident_runner,
    roster,
    stage_roster,
    verification_report,
)
from tests.review.flow_stack import BUCKET, PREFIX, make_event, make_settings

JOB_ID = "job-late-scans"
LATE_FILES = ("stu-017.jpg", "stu-018.jpg")


class BrokenLister:
    async def list_names(self, event, batch):
        raise RuntimeError("bucket listing timed out")


def check_named(report, name: str):
    return next(check for check in report.checks if check.name == name)


async def test_late_scans_block_the_goal_and_reach_the_teacher(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    memory_manager = MemoryManager.from_settings(settings)
    students = roster(6)
    stage_roster(settings, JOB_ID, students, extra_files=LATE_FILES)
    runner, review_store = build_incident_runner(
        settings, memory_manager, CrashingEvaluator(healthy=students)
    )

    record = await runner.process(make_event(JOB_ID))

    assert record.stage == JobStage.COMPLETED
    report = await verification_report(settings, JOB_ID)
    assert report.missing_files is not None
    assert report.missing_files.checked is True
    assert report.missing_files.manifest_count == 6
    assert report.missing_files.listed_count == 8
    assert report.missing_files.missing == list(LATE_FILES)
    assert report.passed is False
    completeness = check_named(report, CHECK_BATCH_FILES_COMPLETE)
    assert completeness.passed is False
    assert "arrived after grading started" in completeness.detail

    pending = await review_store.list_pending()
    late = [item for item in pending if item.kind == ReviewKind.MISSING_FILE]
    assert [item.student_id for item in late] == ["stu-017", "stu-018"]
    assert all(translate_reasons(item.reasons) == [LATE_SCAN] for item in late)
    assert late[0].document_paths == [f"gs://{BUCKET}/{PREFIX}/stu-017.jpg"]


async def test_listing_failure_degrades_to_unchecked(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    students = roster(3)
    stage_roster(settings, JOB_ID, students)
    batch = _batch_from_manifest(settings, JOB_ID, students)

    report = await compare_batch_objects(make_event(JOB_ID), batch, BrokenLister())

    assert report.checked is False
    assert report.missing == []
    assert "batch listing unavailable" in report.detail


async def test_local_lister_only_counts_gradable_objects(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    students = roster(3)
    stage_roster(settings, JOB_ID, students, extra_files=("notes.txt", "stu-009.png"))
    batch = _batch_from_manifest(settings, JOB_ID, students)

    report = await compare_batch_objects(
        make_event(JOB_ID),
        batch,
        LocalBatchLister(staging_dir=settings.gcs_local_staging_dir),
    )

    assert report.checked is True
    assert report.listed_count == 4
    assert report.missing == ["stu-009.png"]


def _batch_from_manifest(settings, job_id: str, students: tuple[str, ...]):
    from autocurricula.core.orchestration.catalog import MANIFEST_NAME, BatchManifest

    root = settings.gcs_local_staging_dir / BUCKET / PREFIX
    manifest = BatchManifest.model_validate_json(
        (root / MANIFEST_NAME).read_text(encoding="utf-8")
    )
    return manifest.batch
