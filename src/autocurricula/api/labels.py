from fastapi import APIRouter, Depends, Query, Request
from pydantic import Field

from autocurricula.api.dependencies import AppContainer, get_container
from autocurricula.api.webhooks import require_push_token
from autocurricula.core.review.label_store import DEFAULT_LABEL_LIMIT
from autocurricula.schemas.common import StrictBaseModel
from autocurricula.schemas.labels import Label

MAX_LABEL_LIMIT = 1000

labels_router = APIRouter(tags=["labels"])


class LabelsResponse(StrictBaseModel):
    items: list[Label] = Field(default_factory=list)
    count: int = Field(ge=0)


@labels_router.get("/labels", response_model=LabelsResponse)
async def list_labels(
    request: Request,
    job_id: str | None = Query(default=None, min_length=1),
    limit: int = Query(default=DEFAULT_LABEL_LIMIT, ge=1, le=MAX_LABEL_LIMIT),
    container: AppContainer = Depends(get_container),
) -> LabelsResponse:
    require_push_token(request, container.settings.pubsub_push_token)
    items = await container.review_service.label_store.list_labels(
        job_id=job_id, limit=limit
    )
    return LabelsResponse(items=items, count=len(items))
