from datetime import datetime, timezone

from autocurricula.config.settings import Settings
from autocurricula.core.memory.manager import MemoryManager
from autocurricula.core.review import LocalReviewStore, ReviewService
from autocurricula.schemas.common import utc_now
from autocurricula.schemas.provenance import Provenance
from autocurricula.schemas.review import ReviewItem
from autocurricula.schemas.sis_sync import SISGradeRecord
from autocurricula.tools.sis_connector import LocalSISConnector

GRADED_AT = datetime(2026, 8, 17, 11, 0, tzinfo=timezone.utc)
SUBJECT = "matematicas"
CEILINGS = {"crit-a": 4.0, "crit-b": 6.0}
MACHINE = {"crit-a": 2.0, "crit-b": 3.0}
PROMPT_SHA = "a" * 64


def make_item(review_id: str, student_id: str, job_id: str) -> ReviewItem:
    return ReviewItem(
        review_id=review_id,
        job_id=job_id,
        student_id=student_id,
        subject=SUBJECT,
        reasons=["crit-a confidence 0.620 below threshold 0.85"],
        document_paths=[f"gs://exams/{job_id}/{student_id}.jpg"],
        proposed_record=SISGradeRecord(
            student_id=student_id,
            subject=SUBJECT,
            score=5.0,
            percentage=50.0,
            feedback="quarantined feedback",
            competency_codes=["MAT.8.1"],
            provenance=Provenance(
                prompt_variant_id="grading-v1", prompt_version_sha=PROMPT_SHA
            ),
            graded_at=GRADED_AT,
        ),
        created_at=utc_now(),
    )


def build_service(settings: Settings) -> tuple[ReviewService, MemoryManager]:
    memory_manager = MemoryManager.from_settings(settings)
    service = ReviewService(
        store=LocalReviewStore(data_dir=settings.local_data_dir),
        sis_connector=LocalSISConnector(data_dir=settings.local_data_dir),
        memory_manager=memory_manager,
    )
    return service, memory_manager


async def seed(service: ReviewService, review_id: str, job_id: str) -> ReviewItem:
    item = make_item(review_id, review_id.split(":")[-1], job_id)
    await service.store.put(item)
    return item
