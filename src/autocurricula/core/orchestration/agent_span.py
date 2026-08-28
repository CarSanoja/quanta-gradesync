from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from autocurricula.core.fleet import annotate_span

__all__ = ["agent_span"]


@contextmanager
def agent_span(
    recorder: Any,
    name: str,
    agent_id: str,
    *,
    stage: str | None = None,
    attributes: dict[str, Any] | None = None,
) -> Iterator[Any]:
    """Open a span that carries the identity of the agent doing the work.

    The live board attributes an event to an agent only when the span carries
    `agent.id`; without it the work lands in the unattributed pile and the
    agent's card stays dark even while it runs. The recorder is optional on a
    job context, so this yields None rather than forcing every caller to guard.
    """
    if recorder is None:
        yield None
        return
    with recorder.span(name, stage=stage, attributes=attributes) as span:
        annotate_span(span, agent_id)
        yield span
