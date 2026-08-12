from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import Field

from autocurricula.api.dependencies import AppContainer, get_container
from autocurricula.api.webhooks import require_push_token
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


def _review_error(error: Exception) -> HTTPException:
    if isinstance(error, ReviewNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    if isinstance(error, ReviewStateError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)
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
    try:
        return await container.review_service.approve(review_id)
    except (ReviewNotFoundError, ReviewStateError, ReviewApprovalError) as error:
        raise _review_error(error) from error


@review_router.post("/review/{review_id}/dismiss", response_model=ReviewItem)
async def dismiss_review(
    review_id: str,
    request: Request,
    container: AppContainer = Depends(get_container),
) -> ReviewItem:
    require_push_token(request, container.settings.pubsub_push_token)
    try:
        return await container.review_service.dismiss(review_id)
    except (ReviewNotFoundError, ReviewStateError) as error:
        raise _review_error(error) from error
