from autocurricula.core.memory.manager import MemoryManager
from autocurricula.core.review.store import ReviewStore
from autocurricula.schemas.common import utc_now
from autocurricula.schemas.review import ReviewItem, ReviewStatus
from autocurricula.schemas.sis_sync import SISWriteRequest
from autocurricula.tools.sis_connector import SISConnector


class ReviewNotFoundError(Exception):
    pass


class ReviewStateError(Exception):
    pass


class ReviewApprovalError(Exception):
    pass


class ReviewService:
    def __init__(
        self,
        store: ReviewStore,
        sis_connector: SISConnector,
        memory_manager: MemoryManager,
    ) -> None:
        self._store = store
        self._sis_connector = sis_connector
        self._memory_manager = memory_manager

    @property
    def store(self) -> ReviewStore:
        return self._store

    async def list_pending(self) -> list[ReviewItem]:
        return await self._store.list_pending()

    async def approve(self, review_id: str) -> ReviewItem:
        item = await self._load_pending(review_id)
        result = await self._sis_connector.write_grades(
            SISWriteRequest(job_id=item.job_id, records=[item.proposed_record])
        )
        if result.failed_count > 0 or result.succeeded_count != 1:
            raise ReviewApprovalError(
                f"sis write failed for review {review_id}: {result.per_record_statuses}"
            )
        await self._memory_manager.persist_student_percentage(
            student_id=item.student_id,
            term=self._resolve_term(item),
            percentage=item.proposed_record.percentage,
        )
        return await self._decide(item, ReviewStatus.APPROVED)

    async def dismiss(self, review_id: str) -> ReviewItem:
        item = await self._load_pending(review_id)
        return await self._decide(item, ReviewStatus.DISMISSED)

    def _resolve_term(self, item: ReviewItem) -> str:
        event = item.proposed_record.graded_at
        return f"term-{event.strftime('%Y-%m')}"

    async def _load_pending(self, review_id: str) -> ReviewItem:
        item = await self._store.get(review_id)
        if item is None:
            raise ReviewNotFoundError(f"no review item {review_id!r}")
        if item.status != ReviewStatus.PENDING:
            raise ReviewStateError(
                f"review item {review_id!r} is already {item.status.value}"
            )
        return item

    async def _decide(self, item: ReviewItem, status: ReviewStatus) -> ReviewItem:
        decided = item.model_copy(
            update={"status": status, "decided_at": utc_now()}
        )
        await self._store.put(decided)
        return decided
