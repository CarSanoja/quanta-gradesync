from collections.abc import Mapping

from autocurricula.core.memory.manager import MemoryManager
from autocurricula.core.review.label_store import LabelStore, label_store_for
from autocurricula.core.review.labels import (
    confirmation_label,
    correction_label,
    rejection_label,
)
from autocurricula.core.review.override import (
    OverrideValidationError,
    build_corrected_record,
    validate_override_scores,
)
from autocurricula.core.review.store import ReviewStore
from autocurricula.schemas.common import utc_now
from autocurricula.schemas.labels import Label
from autocurricula.schemas.memory import FactSource
from autocurricula.schemas.review import ReviewItem, ReviewStatus
from autocurricula.schemas.sis_sync import SISGradeRecord, SISWriteRequest
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
        label_store: LabelStore | None = None,
    ) -> None:
        self._store = store
        self._sis_connector = sis_connector
        self._memory_manager = memory_manager
        self._label_store = (
            label_store if label_store is not None else label_store_for(store)
        )

    @property
    def store(self) -> ReviewStore:
        return self._store

    @property
    def label_store(self) -> LabelStore:
        return self._label_store

    async def list_pending(self) -> list[ReviewItem]:
        return await self._store.list_pending()

    async def list_recent(self, limit: int = 500) -> list[ReviewItem]:
        return await self._store.list_recent(limit)

    async def approve(
        self,
        review_id: str,
        *,
        machine_scores: Mapping[str, float] | None = None,
        ceilings: Mapping[str, float] | None = None,
    ) -> ReviewItem:
        item = await self._load_pending(review_id)
        await self._write_to_sis(item, item.proposed_record)
        await self._persist_percentage(
            item, item.proposed_record.percentage, FactSource.HUMAN_APPROVAL
        )
        await self._emit(
            confirmation_label(item, machine_scores=machine_scores, ceilings=ceilings)
        )
        return await self._decide(item, ReviewStatus.APPROVED)

    async def dismiss(
        self,
        review_id: str,
        *,
        machine_scores: Mapping[str, float] | None = None,
        ceilings: Mapping[str, float] | None = None,
    ) -> ReviewItem:
        item = await self._load_pending(review_id)
        await self._emit(
            rejection_label(item, machine_scores=machine_scores, ceilings=ceilings)
        )
        return await self._decide(item, ReviewStatus.DISMISSED)

    async def override(
        self,
        review_id: str,
        scores: Mapping[str, float],
        *,
        note: str | None = None,
        machine_scores: Mapping[str, float] | None = None,
        ceilings: Mapping[str, float] | None = None,
    ) -> ReviewItem:
        item = await self._load_pending(review_id)
        total_ceiling = validate_override_scores(item, scores, ceilings)
        corrected = build_corrected_record(item, scores, total_ceiling, note)
        await self._write_to_sis(item, corrected)
        await self._persist_percentage(
            item, corrected.percentage, FactSource.HUMAN_OVERRIDE
        )
        await self._emit(
            correction_label(
                item,
                dict(scores),
                corrected.percentage,
                machine_scores=machine_scores,
                ceilings=ceilings,
                note=note,
            )
        )
        return await self._decide(
            item,
            ReviewStatus.OVERRIDDEN,
            corrected_record=corrected,
            reviewer_note=note,
        )

    def _resolve_term(self, item: ReviewItem) -> str:
        event = item.proposed_record.graded_at
        return f"term-{event.strftime('%Y-%m')}"

    async def _write_to_sis(self, item: ReviewItem, record: SISGradeRecord) -> None:
        result = await self._sis_connector.write_grades(
            SISWriteRequest(job_id=item.job_id, records=[record])
        )
        if result.failed_count > 0 or result.succeeded_count != 1:
            raise ReviewApprovalError(
                f"sis write failed for review {item.review_id}: "
                f"{result.per_record_statuses}"
            )

    async def _persist_percentage(
        self, item: ReviewItem, percentage: float, source: FactSource
    ) -> None:
        await self._memory_manager.persist_student_percentage(
            student_id=item.student_id,
            term=self._resolve_term(item),
            percentage=percentage,
            job_id=item.job_id,
            source=source,
        )

    async def _emit(self, label: Label) -> None:
        await self._label_store.put(label)

    async def _load_pending(self, review_id: str) -> ReviewItem:
        item = await self._store.get(review_id)
        if item is None:
            raise ReviewNotFoundError(f"no review item {review_id!r}")
        if item.status != ReviewStatus.PENDING:
            raise ReviewStateError(
                f"review item {review_id!r} is already {item.status.value}"
            )
        return item

    async def _decide(
        self,
        item: ReviewItem,
        status: ReviewStatus,
        corrected_record: SISGradeRecord | None = None,
        reviewer_note: str | None = None,
    ) -> ReviewItem:
        update: dict[str, object] = {"status": status, "decided_at": utc_now()}
        if corrected_record is not None:
            update["corrected_record"] = corrected_record
        if reviewer_note is not None:
            update["reviewer_note"] = reviewer_note
        decided = item.model_copy(update=update)
        await self._store.put(decided)
        return decided


__all__ = [
    "OverrideValidationError",
    "ReviewApprovalError",
    "ReviewNotFoundError",
    "ReviewService",
    "ReviewStateError",
]
