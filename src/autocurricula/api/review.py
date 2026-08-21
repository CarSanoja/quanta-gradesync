from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import FileResponse
from pydantic import Field

from autocurricula.api.dependencies import AppContainer, get_container
from autocurricula.api.media import (
    DocumentAccessError,
    DocumentMissingError,
    load_remote_document,
    media_type_for,
    resolve_document,
)
from autocurricula.api.review_context import ReviewContext, load_review_context
from autocurricula.api.webhooks import require_push_token
from autocurricula.core.review.override import OverrideValidationError
from autocurricula.core.review.service import (
    ReviewApprovalError,
    ReviewNotFoundError,
    ReviewStateError,
)
from autocurricula.schemas.common import StrictBaseModel
from autocurricula.schemas.review import ReviewItem

review_router = APIRouter(tags=["review"])


class PendingReviewsResponse(StrictBaseModel):
    items: list[ReviewItem] = Field(default_factory=list)
    count: int = Field(ge=0)


class CriterionOverride(StrictBaseModel):
    criterion_id: str = Field(min_length=1)
    score: float = Field(ge=0)


class ReviewOverrideRequest(StrictBaseModel):
    scores: list[CriterionOverride] = Field(min_length=1)
    note: str | None = Field(default=None, max_length=2000)

    def as_mapping(self) -> dict[str, float]:
        mapping: dict[str, float] = {}
        for entry in self.scores:
            if entry.criterion_id in mapping:
                raise ValueError(
                    f"criterion {entry.criterion_id!r} appears more than once"
                )
            mapping[entry.criterion_id] = entry.score
        return mapping


def _review_error(error: Exception) -> HTTPException:
    if isinstance(error, ReviewNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    if isinstance(error, ReviewStateError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))
    if isinstance(error, OverrideValidationError):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        )
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)
    )


async def _decision_context(
    container: AppContainer, review_id: str
) -> ReviewContext:
    item = await container.review_service.store.get(review_id)
    if item is None:
        raise _review_error(ReviewNotFoundError(f"no review item {review_id!r}"))
    return await load_review_context(
        item, container.checkpoint_store, container.catalog
    )


@review_router.get("/review/pending", response_model=PendingReviewsResponse)
async def list_pending_reviews(
    request: Request,
    container: AppContainer = Depends(get_container),
) -> PendingReviewsResponse:
    require_push_token(request, container.settings.pubsub_push_token)
    items = await container.review_service.list_pending()
    return PendingReviewsResponse(items=items, count=len(items))


@review_router.post("/review/{review_id}/approve", response_model=ReviewItem)
async def approve_review(
    review_id: str,
    request: Request,
    container: AppContainer = Depends(get_container),
) -> ReviewItem:
    require_push_token(request, container.settings.pubsub_push_token)
    context = await _decision_context(container, review_id)
    try:
        return await container.review_service.approve(
            review_id,
            machine_scores=context.machine_scores,
            ceilings=context.ceilings,
        )
    except (ReviewNotFoundError, ReviewStateError, ReviewApprovalError) as error:
        raise _review_error(error) from error


@review_router.post("/review/{review_id}/dismiss", response_model=ReviewItem)
async def dismiss_review(
    review_id: str,
    request: Request,
    container: AppContainer = Depends(get_container),
) -> ReviewItem:
    require_push_token(request, container.settings.pubsub_push_token)
    context = await _decision_context(container, review_id)
    try:
        return await container.review_service.dismiss(
            review_id,
            machine_scores=context.machine_scores,
            ceilings=context.ceilings,
        )
    except (ReviewNotFoundError, ReviewStateError) as error:
        raise _review_error(error) from error


@review_router.post("/review/{review_id}/override", response_model=ReviewItem)
async def override_review(
    review_id: str,
    payload: ReviewOverrideRequest,
    request: Request,
    container: AppContainer = Depends(get_container),
) -> ReviewItem:
    require_push_token(request, container.settings.pubsub_push_token)
    context = await _decision_context(container, review_id)
    try:
        scores = payload.as_mapping()
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error
    try:
        return await container.review_service.override(
            review_id,
            scores,
            note=payload.note,
            machine_scores=context.machine_scores,
            ceilings=context.ceilings,
        )
    except (
        ReviewNotFoundError,
        ReviewStateError,
        ReviewApprovalError,
        OverrideValidationError,
    ) as error:
        raise _review_error(error) from error


@review_router.get("/review/{review_id}/page-image")
async def review_page_image(
    review_id: str,
    request: Request,
    index: int = Query(default=0, ge=0),
    container: AppContainer = Depends(get_container),
) -> Response:
    require_push_token(request, container.settings.pubsub_push_token)
    item = await container.review_service.store.get(review_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"no review item {review_id!r}"
        )
    if index >= len(item.document_paths):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"review item {review_id!r} has no document at index {index}",
        )
    reference = item.document_paths[index]
    try:
        if not container.settings.local_mode:
            payload, media_type = await load_remote_document(
                container.settings, reference
            )
            return Response(content=payload, media_type=media_type)
        path = resolve_document(container.settings, reference)
    except DocumentAccessError as error:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(error)
        ) from error
    except DocumentMissingError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        ) from error
    return FileResponse(path, media_type=media_type_for(path))
