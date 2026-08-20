from typing import Literal

from autocurricula.schemas.common import StrictBaseModel


class HealthResponse(StrictBaseModel):
    status: str = "ok"


class ReadinessResponse(StrictBaseModel):
    status: Literal["ready", "unavailable"]
    mode: Literal["local", "gcp"]
    reason: str | None = None


class WebhookResult(StrictBaseModel):
    job_id: str
    status: Literal["completed", "duplicate", "ignored"]
    stage: str | None = None
    reason: str | None = None
