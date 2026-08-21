from collections.abc import Mapping
from typing import Any

from pydantic import Field

from autocurricula.schemas.common import StrictBaseModel

FEEDBACK_FIELD = "student_feedback"


class TeacherFeedbackPoint(StrictBaseModel):
    text: str
    page: int | None = None
    quote: str | None = None


class TeacherFeedbackView(StrictBaseModel):
    band: str | None = None
    headline: str | None = None
    strengths: list[TeacherFeedbackPoint] = Field(default_factory=list)
    growth: list[TeacherFeedbackPoint] = Field(default_factory=list)
    next_step: str | None = None
    teacher_note: str | None = None

    def is_empty(self) -> bool:
        return not (
            self.headline
            or self.strengths
            or self.growth
            or self.next_step
            or self.teacher_note
        )


def as_mapping(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, Mapping):
        return dict(value)
    dump = getattr(value, "model_dump", None)
    if not callable(dump):
        return None
    try:
        return dict(dump(mode="json"))
    except Exception:
        return None


def as_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    return trimmed or None


def as_page(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value >= 1 else None


def as_point(raw: Any) -> TeacherFeedbackPoint | None:
    data = as_mapping(raw)
    if data is None:
        return None
    text = as_text(data.get("text"))
    if text is None:
        return None
    evidence = as_mapping(data.get("evidence")) or {}
    return TeacherFeedbackPoint(
        text=text,
        page=as_page(evidence.get("page")),
        quote=as_text(evidence.get("quote")),
    )


def as_points(raw: Any) -> list[TeacherFeedbackPoint]:
    if not isinstance(raw, (list, tuple)):
        return []
    points = (as_point(entry) for entry in raw)
    return [point for point in points if point is not None]


def build_feedback_view(*sources: Any) -> TeacherFeedbackView | None:
    for source in sources:
        data = as_mapping(getattr(source, FEEDBACK_FIELD, None))
        if not data:
            continue
        view = TeacherFeedbackView(
            band=as_text(data.get("band")),
            headline=as_text(data.get("headline")),
            strengths=as_points(data.get("strengths")),
            growth=as_points(data.get("growth")),
            next_step=as_text(data.get("next_step")),
            teacher_note=as_text(data.get("teacher_note")),
        )
        if not view.is_empty():
            return view
    return None


__all__ = [
    "TeacherFeedbackPoint",
    "TeacherFeedbackView",
    "build_feedback_view",
]
