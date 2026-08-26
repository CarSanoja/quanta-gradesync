import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from autocurricula.core.telemetry.live_bridge import LiveBridge, scalar_attributes
from autocurricula.core.telemetry.live_context import SCOPE_KEYS, update_scope
from autocurricula.core.telemetry.live_sink import LiveSink
from autocurricula.schemas.telemetry import SpanStatus, TypedSpan


class SpanHandle:
    def __init__(self, recorder: "Recorder", span_id: str) -> None:
        self._recorder = recorder
        self.span_id = span_id
        self.attributes: dict[str, Any] = {}

    def set(self, key: str, value: Any) -> None:
        self.attributes[key] = value
        if key in SCOPE_KEYS:
            update_scope(key, value)


class Recorder:
    def __init__(
        self, trace_id: str, *, sink: LiveSink | None = None, job_id: str = ""
    ) -> None:
        self._trace_id = trace_id
        self._by_id: dict[str, TypedSpan] = {}
        self._creation: list[str] = []
        self._counter = 0
        self._lock = threading.Lock()
        self._bridge = LiveBridge(trace_id=trace_id, sink=sink, job_id=job_id)

    @property
    def trace_id(self) -> str:
        return self._trace_id

    @property
    def spans(self) -> list[TypedSpan]:
        return [
            self._by_id[span_id]
            for span_id in self._creation
            if span_id in self._by_id
        ]

    @contextmanager
    def span(
        self,
        name: str,
        *,
        parent: "SpanHandle | None" = None,
        stage: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> Iterator[SpanHandle]:
        handle = self._open(attributes)
        parent_id = parent.span_id if parent is not None else None
        started = time.monotonic()
        with self._bridge.observe(
            handle, name=name, stage=stage, parent_span_id=parent_id
        ):
            try:
                yield handle
            except Exception as error:
                handle.set("error.type", type(error).__name__)
                self._record(handle, name, parent_id, stage, started, SpanStatus.ERROR)
                raise
            self._record(handle, name, parent_id, stage, started, SpanStatus.OK)

    def _open(self, attributes: dict[str, Any] | None) -> SpanHandle:
        with self._lock:
            self._counter += 1
            span_id = f"sp{self._counter:04d}"
            self._creation.append(span_id)
        handle = SpanHandle(self, span_id)
        handle.attributes.update(attributes or {})
        return handle

    def _record(
        self,
        handle: SpanHandle,
        name: str,
        parent_id: str | None,
        stage: str | None,
        started: float,
        status: SpanStatus,
    ) -> None:
        self._by_id[handle.span_id] = TypedSpan(
            name=name,
            trace_id=self._trace_id,
            span_id=handle.span_id,
            parent_id=parent_id,
            stage=stage,
            status=status,
            duration_ms=round((time.monotonic() - started) * 1000.0, 3),
            attributes=scalar_attributes(handle.attributes),
        )

    def tree(self) -> dict[str, Any]:
        by_id = dict(self._by_id)
        children: dict[str | None, list[TypedSpan]] = {}
        for span in self.spans:
            children.setdefault(span.parent_id, []).append(span)
        return {
            "trace_id": self._trace_id,
            "root": _node(None, children, by_id),
        }


def _node(
    span_id: str | None,
    children: dict[str | None, list[TypedSpan]],
    by_id: dict[str, TypedSpan],
) -> Any:
    if span_id is None:
        return [
            _node(child.span_id, children, by_id) for child in children.get(None, [])
        ]
    span = by_id[span_id]
    return {
        "span": span.model_dump(),
        "children": [
            _node(child.span_id, children, by_id)
            for child in children.get(span_id, [])
        ],
    }
