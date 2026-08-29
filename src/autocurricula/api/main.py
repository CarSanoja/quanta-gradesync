from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import APIRouter, Depends, FastAPI
from fastapi.responses import JSONResponse

from autocurricula import __version__
from autocurricula.api.console import console_router
from autocurricula.api.dependencies import (
    AppContainer,
    build_container,
    get_container,
    set_container,
)
from autocurricula.api.fleet import fleet_router
from autocurricula.api.gate import build_gate
from autocurricula.api.ingest import ingest_router
from autocurricula.api.jobs import jobs_router
from autocurricula.api.labels import labels_router
from autocurricula.api.live import live_router
from autocurricula.api.optimizer import optimizer_router
from autocurricula.api.readiness import (
    BackendUnavailable,
    ping_backend,
    settings_issues,
)
from autocurricula.api.responses import HealthResponse, ReadinessResponse
from autocurricula.api.review import review_router
from autocurricula.api.sis_ledger import sis_router
from autocurricula.api.teacher import teacher_router
from autocurricula.api.trace import trace_router
from autocurricula.api.webhooks import pubsub_router
from autocurricula.config.genai_env import configure_genai_env
from autocurricula.core.telemetry import (
    LlmSpanCapture,
    install_structured_logging,
    install_telemetry,
)

APP_TITLE = "AutoCurricula & GradeSync Engine"

health_router = APIRouter(tags=["health"])


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    container = build_container()
    configure_genai_env(container.settings)
    install_structured_logging(container.settings)
    install_telemetry(container.settings, LlmSpanCapture(container.settings))
    set_container(app, container)
    try:
        yield
    finally:
        for task in list(container.in_flight):
            task.cancel()
        container.in_flight.clear()


@health_router.get("/healthz", response_model=HealthResponse)
async def healthz() -> HealthResponse:
    return HealthResponse()


def unready(mode: Literal["local", "gcp"], reason: str) -> JSONResponse:
    payload = ReadinessResponse(status="unavailable", mode=mode, reason=reason)
    return JSONResponse(status_code=503, content=payload.model_dump(exclude_none=True))


@health_router.get(
    "/readyz", response_model=ReadinessResponse, response_model_exclude_none=True
)
async def readyz(
    container: AppContainer = Depends(get_container),
) -> ReadinessResponse:
    mode: Literal["local", "gcp"] = (
        "local" if container.settings.local_mode else "gcp"
    )
    issues = settings_issues(container.settings)
    if issues:
        return unready(mode, "; ".join(issues))
    try:
        resolved_mode = await ping_backend(container.settings)
    except (BackendUnavailable, TimeoutError) as error:
        return unready(mode, str(error))
    return ReadinessResponse(status="ready", mode=resolved_mode)


def create_app() -> FastAPI:
    application = FastAPI(title=APP_TITLE, version=__version__, lifespan=lifespan)
    # Before any router: one gate, so a new route is protected by default and an
    # unauthenticated caller cannot reach body validation and read a schema back
    # out of the 422. /openapi.json is behind it too.
    application.middleware("http")(build_gate())
    application.include_router(health_router)
    application.include_router(pubsub_router)
    application.include_router(review_router)
    application.include_router(labels_router)
    application.include_router(jobs_router)
    application.include_router(trace_router)
    application.include_router(live_router)
    application.include_router(sis_router)
    application.include_router(ingest_router)
    application.include_router(optimizer_router)
    application.include_router(fleet_router)
    application.include_router(console_router)
    application.include_router(teacher_router)
    return application


app = create_app()
