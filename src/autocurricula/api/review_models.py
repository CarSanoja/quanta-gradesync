from fastapi import HTTPException, status
from pydantic import Field

from autocurricula.core.review.override import OverrideValidationError
from autocurricula.core.review.service import ReviewNotFoundError, ReviewStateError
from autocurricula.schemas.common import StrictBaseModel
from autocurricula.schemas.review import ReviewItem


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


def review_error(error: Exception) -> HTTPException:
    if isinstance(error, ReviewNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    if isinstance(error, ReviewStateError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))
    if isinstance(error, OverrideValidationError):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        )
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error))


__all__ = [
    "CriterionOverride",
    "PendingReviewsResponse",
    "ReviewOverrideRequest",
    "review_error",
]
