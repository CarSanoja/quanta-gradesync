from datetime import datetime, timezone
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field


class StrictBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FrozenStrictModel(StrictBaseModel):
    model_config = ConfigDict(frozen=True)


JobId = Annotated[str, Field(min_length=1)]
StudentId = Annotated[str, Field(min_length=1)]
ExamId = Annotated[str, Field(min_length=1)]
ClassId = Annotated[str, Field(min_length=1)]


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


TzAwareDatetime = Annotated[datetime, AfterValidator(_ensure_utc)]


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)
