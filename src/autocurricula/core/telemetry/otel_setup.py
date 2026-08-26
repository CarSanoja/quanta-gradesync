import logging
import os
from typing import Any

from autocurricula.config.settings import Settings
from autocurricula.core.telemetry.llm_capture import LlmSpanCapture

logger = logging.getLogger(__name__)

CAPTURE_CONTENT_ENV = "ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS"
SERVICE_NAME_ENV = "OTEL_SERVICE_NAME"
SERVICE_NAME = "autocurricula-gradesync"

_installed = False


def gcp_hooks(settings: Settings) -> Any | None:
    if settings.local_mode or not settings.telemetry_cloud_trace_enabled:
        return None
    try:
        from google.adk.telemetry.google_cloud import get_gcp_exporters

        return get_gcp_exporters(
            enable_cloud_tracing=True,
            enable_cloud_metrics=settings.telemetry_cloud_metrics_enabled,
        )
    except Exception as error:
        logger.warning("cloud trace exporters unavailable: %s", error)
        return None


def install_telemetry(settings: Settings, capture: LlmSpanCapture) -> bool:
    global _installed
    if _installed:
        return False
    _installed = True
    if not settings.telemetry_capture_content:
        os.environ[CAPTURE_CONTENT_ENV] = "false"
    os.environ.setdefault(SERVICE_NAME_ENV, SERVICE_NAME)
    try:
        from google.adk.telemetry.setup import OTelHooks, maybe_set_otel_providers

        hooks = [OTelHooks(span_processors=[capture])]
        exporters = gcp_hooks(settings)
        if exporters is not None:
            hooks.append(exporters)
        maybe_set_otel_providers(hooks)
    except Exception as error:
        logger.warning("otel provider setup failed: %s", error)
        return False
    return True


def reset_telemetry_install() -> None:
    global _installed
    _installed = False
