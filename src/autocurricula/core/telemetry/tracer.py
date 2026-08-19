import time
from contextlib import contextmanager
from typing import Any, Iterator

from autocurricula.schemas.telemetry import SpanStatus, TypedSpan


class SpanHandle:
    def __init__(self, recorder: "Recorder", span_id: str) -> None:
        self._recorder = recorder
        self.span_id = span_id
        self.attributes: dict[str, Any] = {}

    def set(self, key: str, value: Any) -> None:
        self.attributes[key] = value


class Recorder:
    def __init__(self, trace_id: str) -> None:
        self._trace_id = trace_id
        self._by_id: dict[str, TypedSpan] = {}
        self._creation: list[str] = []
        self._counter = 0

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
        self._counter += 1
        span_id = f"sp{self._counter:04d}"
        self._creation.append(span_id)
        handle = SpanHandle(self, span_id)
        handle.attributes.update(attributes or {})
        started = time.monotonic()
        try:
            yield handle
        except Exception as error:
            handle.set("error.type", type(error).__name__)
            self._record(handle, name, span_id, parent, stage, started, SpanStatus.ERROR)
            raise
        self._record(handle, name, span_id, parent, stage, started, SpanStatus.OK)

    def _record(
        self,
        handle: SpanHandle,
        name: str,
        span_id: str,
        parent: "SpanHandle | None",
        stage: str | None,
        started: float,
        status: SpanStatus,
    ) -> None:
        self._by_id[span_id] = TypedSpan(
            name=name,
            trace_id=self._trace_id,
            span_id=span_id,
            parent_id=parent.span_id if parent is not None else None,
            stage=stage,
            status=status,
            duration_ms=round((time.monotonic() - started) * 1000.0, 3),
            attributes={
                key: value
                for key, value in handle.attributes.items()
                if isinstance(value, (str, bool, int, float))
            },
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
