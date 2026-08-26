import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

from opentelemetry import trace

from autocurricula.config.settings import Settings

TRACE_FIELD = "logging.googleapis.com/trace"
SPAN_FIELD = "logging.googleapis.com/spanId"

SEVERITIES = {
    "DEBUG": "DEBUG",
    "INFO": "INFO",
    "WARNING": "WARNING",
    "ERROR": "ERROR",
    "CRITICAL": "CRITICAL",
    "NOTSET": "DEFAULT",
}


class JsonLogFormatter(logging.Formatter):
    def __init__(self, project_id: str = "") -> None:
        super().__init__()
        self._project_id = project_id

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "severity": SEVERITIES.get(record.levelname, "DEFAULT"),
            "message": record.getMessage(),
            "logger": record.name,
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
        }
        fields = getattr(record, "json_fields", None)
        if isinstance(fields, dict):
            payload.update(fields)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        payload.update(self._correlation())
        return json.dumps(payload, default=str)

    def _correlation(self) -> dict[str, str]:
        try:
            context = trace.get_current_span().get_span_context()
        except Exception:
            return {}
        if not context.is_valid:
            return {}
        fields = {SPAN_FIELD: f"{context.span_id:016x}"}
        if self._project_id:
            fields[TRACE_FIELD] = (
                f"projects/{self._project_id}/traces/{context.trace_id:032x}"
            )
        return fields


def install_structured_logging(settings: Settings) -> bool:
    if not settings.resolved_log_json:
        return False
    root = logging.getLogger()
    if any(isinstance(handler.formatter, JsonLogFormatter) for handler in root.handlers):
        return False
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(JsonLogFormatter(settings.gcp_project_id))
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    return True
