from pathlib import Path

from autocurricula.core.memory.manager import MemoryManager
from autocurricula.core.orchestration.job_state import JobStage
from autocurricula.core.review import ReviewStateError
from tests.review.flow_stack import (
    BUCKET,
    LOW_CONFIDENCE_STUDENT,
    PREFIX,
    build_stack,
    make_event,
    make_settings,
    stage_batch,
    written_students,
)


async def test_low_confidence_submission_is_quarantined_not_synced(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    memory_manager = MemoryManager.from_settings(settings)
    runner, review_store, service = build_stack(settings, memory_manager)
    stage_batch(settings, "job-flow-001")
    record = await runner.process(make_event("job-flow-001"))
    assert record.stage == JobStage.COMPLETED
    assert written_students(settings) == {"stu-001", "stu-003"}
    pending = await review_store.list_pending()
    assert [item.review_id for item in pending] == ["job-flow-001:stu-002"]
    item = pending[0]
    assert any("confidence" in reason for reason in item.reasons)
    assert item.evidence[0].page == 1
    assert item.evidence[0].quote == f"visible answer of {LOW_CONFIDENCE_STUDENT}"
    assert item.document_paths == [f"gs://{BUCKET}/{PREFIX}/stu-002.jpg"]
    assert item.proposed_record.student_id == "stu-002"
    assert await memory_manager.persistent_store.get_profile("stu-001") is not None
    assert await memory_manager.persistent_store.get_profile("stu-002") is None


async def test_approve_writes_quarantined_record_to_sis_and_l3(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    memory_manager = MemoryManager.from_settings(settings)
    runner, review_store, service = build_stack(settings, memory_manager)
    stage_batch(settings, "job-flow-002")
    await runner.process(make_event("job-flow-002"))
    approved = await service.approve("job-flow-002:stu-002")
    assert approved.status.value == "approved"
    assert approved.decided_at is not None
    assert written_students(settings) == {"stu-001", "stu-002", "stu-003"}
    profile = await memory_manager.persistent_store.get_profile("stu-002")
    assert profile is not None
    snapshot = profile.terms[-1]
    assert snapshot.submissions_count == 1
    assert snapshot.avg_percentage == approved.proposed_record.percentage
    assert await review_store.list_pending() == []
    try:
        await service.approve("job-flow-002:stu-002")
    except ReviewStateError:
        pass
    else:
        raise AssertionError("second approve must fail")


async def test_dismiss_closes_item_without_sis_write(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    memory_manager = MemoryManager.from_settings(settings)
    runner, review_store, service = build_stack(settings, memory_manager)
    stage_batch(settings, "job-flow-003")
    await runner.process(make_event("job-flow-003"))
    dismissed = await service.dismiss("job-flow-003:stu-002")
    assert dismissed.status.value == "dismissed"
    assert written_students(settings) == {"stu-001", "stu-003"}
    assert await review_store.list_pending() == []
