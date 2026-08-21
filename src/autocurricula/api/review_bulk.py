from typing import Self

from fastapi import HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import Field, model_validator

from autocurricula.api.dependencies import AppContainer
from autocurricula.api.review_context import load_review_context
from autocurricula.core.review.bulk import (
    BulkReleaseRefusal,
    BulkReleaseSelection,
    select_by_ids,
    select_by_job,
)
from autocurricula.core.review.override import OverrideValidationError
from autocurricula.core.review.service import (
    ReviewApprovalError,
    ReviewNotFoundError,
    ReviewStateError,
)
from autocurricula.schemas.common import StrictBaseModel
from autocurricula.schemas.review import ReviewItem

MAX_BULK_IDS = 500
SCOPE_ERROR = "send either review_ids or job_id, not both and not neither"
REFUSED_DETAIL = (
    "{count} of these exams need your judgement and cannot be released in bulk; "
    "nothing was released"
)


class BulkReleaseRequest(StrictBaseModel):
    review_ids: list[str] | None = Field(default=None, max_length=MAX_BULK_IDS)
    job_id: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _exactly_one_scope(self) -> Self:
        if bool(self.review_ids) == bool(self.job_id):
            raise ValueError(SCOPE_ERROR)
        return self

    def unique_ids(self) -> list[str]:
        return list(dict.fromkeys(self.review_ids or []))


class BulkReleaseFailure(StrictBaseModel):
    review_id: str
    error: str


class BulkReleaseResponse(StrictBaseModel):
    released: list[str] = Field(default_factory=list)
    released_count: int = Field(ge=0)
    already_released: list[str] = Field(default_factory=list)
    excluded: list[BulkReleaseRefusal] = Field(default_factory=list)
    failed: list[BulkReleaseFailure] = Field(default_factory=list)
    requested_count: int = Field(ge=0)


class BulkReleaseRefused(StrictBaseModel):
    detail: str
    refused: list[BulkReleaseRefusal] = Field(default_factory=list)
    releasable_count: int = Field(ge=0)


async def _selection(
    container: AppContainer, payload: BulkReleaseRequest
) -> BulkReleaseSelection:
    if payload.job_id is not None:
        pending = await container.review_service.list_pending()
        return select_by_job(pending, payload.job_id)
    requested = payload.unique_ids()
    found: dict[str, ReviewItem | None] = {}
    for review_id in requested:
        found[review_id] = await container.review_service.store.get(review_id)
    return select_by_ids(found, requested)


async def _release_one(
    container: AppContainer, item: ReviewItem
) -> tuple[str, str | None]:
    context = await load_review_context(
        item, container.checkpoint_store, container.catalog
    )
    try:
        await container.review_service.approve(
            item.review_id,
            machine_scores=context.machine_scores,
            ceilings=context.ceilings,
        )
    except ReviewStateError:
        return "already", None
    except ReviewNotFoundError as error:
        return "failed", str(error)
    except (ReviewApprovalError, OverrideValidationError) as error:
        return "failed", str(error)
    return "released", None


def _refusal_response(selection: BulkReleaseSelection) -> JSONResponse:
    payload = BulkReleaseRefused(
        detail=REFUSED_DETAIL.format(count=len(selection.refused)),
        refused=selection.refused,
        releasable_count=len(selection.releasable),
    )
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT, content=payload.model_dump(mode="json")
    )


async def bulk_release(
    container: AppContainer, payload: BulkReleaseRequest
) -> JSONResponse | BulkReleaseResponse:
    selection = await _selection(container, payload)
    if selection.refused:
        return _refusal_response(selection)
    if payload.job_id is not None and not selection.releasable:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no exam in job {payload.job_id!r} is held only by the batch rule",
        )
    released: list[str] = []
    already: list[str] = list(selection.already_released)
    failed: list[BulkReleaseFailure] = []
    for item in selection.releasable:
        outcome, error = await _release_one(container, item)
        if outcome == "released":
            released.append(item.review_id)
        elif outcome == "already":
            already.append(item.review_id)
        else:
            failed.append(
                BulkReleaseFailure(review_id=item.review_id, error=error or "unknown")
            )
    return BulkReleaseResponse(
        released=released,
        released_count=len(released),
        already_released=already,
        excluded=selection.excluded,
        failed=failed,
        requested_count=len(selection.releasable) + len(selection.already_released),
    )


__all__ = [
    "MAX_BULK_IDS",
    "SCOPE_ERROR",
    "BulkReleaseFailure",
    "BulkReleaseRefused",
    "BulkReleaseRequest",
    "BulkReleaseResponse",
    "bulk_release",
]
