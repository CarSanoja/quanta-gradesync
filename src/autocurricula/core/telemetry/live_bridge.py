import logging
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from functools import partial
from typing import Any

from autocurricula.core.telemetry.live_context import (
    STUDENT_ID_KEY,
    LiveScope,
    get_scope,
    push_scope,
    reset_scope,
)
from autocurricula.core.telemetry.live_sink import LiveSink
from autocurricula.core.telemetry.otel_spans import (
    job_parent_context,
    mirror_attributes,
    otel_span,
)
from autocurricula.schemas.common import utc_now
from autocurricula.schemas.live_events import LiveEvent, LiveEventKind, LiveEventStatus
from autocurricula.schemas.telemetry import ATTR_AGENT_ID, ATTR_AGENT_PRINCIPAL

logger = logging.getLogger(__name__)

SCALARS = (str, bool, int, float)


def scalar_attributes(attributes: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in attributes.items() if isinstance(value, SCALARS)}


class LiveBridge:
    def __init__(self, *, trace_id: str, sink: LiveSink | None, job_id: str) -> None:
        self._trace_id = trace_id
        self._sink = sink
        self._job_id = job_id
        self._lock = threading.Lock()
        self._seq = 0
        self._context = job_parent_context(trace_id)

    @property
    def enabled(self) -> bool:
        return self._sink is not None and bool(self._job_id)

    def next_seq(self) -> int:
        with self._lock:
            self._seq += 1
            return self._seq

    def emit(self, kind: LiveEventKind, name: str, **fields: Any) -> None:
        if not self.enabled:
            return
        try:
            event = LiveEvent(
                seq=self.next_seq(),
                recorded_at=utc_now().isoformat(),
                job_id=self._job_id,
                trace_id=self._trace_id,
                kind=kind,
                name=name or kind.value,
                **fields,
            )
        except Exception as error:
            logger.warning("live event build failed for job %s: %s", self._job_id, error)
            return
        self._sink.emit(event)

    def emit_scoped(self, scope: LiveScope, kind: LiveEventKind, name: str, **fields: Any) -> None:
        fields.setdefault("stage", scope.stage)
        fields.setdefault("agent_id", scope.agent_id)
        fields.setdefault("student_id", scope.student_id)
        fields.setdefault("parent_span_id", scope.span_id)
        self.emit(kind, name, **fields)

    @contextmanager
    def observe(
        self,
        handle: Any,
        *,
        name: str,
        stage: str | None,
        parent_span_id: str | None,
    ) -> Iterator[None]:
        started = time.monotonic()
        token = self._enter_scope(handle, stage)
        self._emit_span(
            LiveEventKind.SPAN_START,
            handle,
            name=name,
            stage=stage,
            parent_span_id=parent_span_id,
            status=LiveEventStatus.RUNNING,
        )
        status = LiveEventStatus.OK
        try:
            with otel_span(
                name,
                trace_id=self._trace_id,
                job_id=self._job_id,
                stage=stage,
                parent_context=self._context,
            ) as span:
                try:
                    yield
                except BaseException:
                    status = LiveEventStatus.ERROR
                    raise
                finally:
                    mirror_attributes(span, scalar_attributes(handle.attributes))
        finally:
            self._emit_span(
                LiveEventKind.SPAN_END,
                handle,
                name=name,
                stage=stage,
                parent_span_id=parent_span_id,
                status=status,
                duration_ms=round((time.monotonic() - started) * 1000.0, 3),
            )
            reset_scope(token)

    def _enter_scope(self, handle: Any, stage: str | None) -> Any:
        parent = get_scope()
        attributes = handle.attributes
        scope = LiveScope(
            job_id=self._job_id,
            trace_id=self._trace_id,
            next_seq=self.next_seq,
            stage=stage or (parent.stage if parent is not None else None),
            agent_id=attributes.get(ATTR_AGENT_ID)
            or (parent.agent_id if parent is not None else None),
            student_id=attributes.get(STUDENT_ID_KEY)
            or (parent.student_id if parent is not None else None),
            span_id=handle.span_id,
        )
        scope.emit = partial(self.emit_scoped, scope)
        return push_scope(scope)

    def _emit_span(
        self,
        kind: LiveEventKind,
        handle: Any,
        *,
        name: str,
        stage: str | None,
        parent_span_id: str | None,
        status: LiveEventStatus,
        duration_ms: float | None = None,
    ) -> None:
        if not self.enabled:
            return
        attributes = scalar_attributes(handle.attributes)
        scope = get_scope()
        self.emit(
            kind,
            name,
            status=status,
            stage=stage,
            agent_id=attributes.get(ATTR_AGENT_ID)
            or (scope.agent_id if scope is not None else None),
            principal=attributes.get(ATTR_AGENT_PRINCIPAL),
            student_id=attributes.get(STUDENT_ID_KEY)
            or (scope.student_id if scope is not None else None),
            span_id=handle.span_id,
            parent_span_id=parent_span_id,
            duration_ms=duration_ms,
            attributes=attributes,
        )
