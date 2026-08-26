import json
from datetime import UTC, datetime
from pathlib import Path

from autocurricula.schemas.curriculum import Competency, CurriculumStandard
from autocurricula.schemas.events import PubSubJobEvent
from autocurricula.schemas.rubric import MasteryLevel, Rubric, RubricCriterion

BUCKET = "exams"
PREFIX = "batches/2026_matematicas_10A_Parcial1"
TRIGGERED_AT = datetime(2026, 8, 17, 9, 0, tzinfo=UTC)


def make_event(
    prefix: str = PREFIX,
    subject: str = "matematicas",
    class_id: str = "10A",
    job_id: str = "job-infer-001",
) -> PubSubJobEvent:
    return PubSubJobEvent(
        job_id=job_id,
        bucket=BUCKET,
        exam_batch_prefix=prefix,
        class_id=class_id,
        subject=subject,
        triggered_at=TRIGGERED_AT,
    )


def make_rubric() -> Rubric:
    return Rubric(
        rubric_id="rub-mat-001",
        subject="matematicas",
        version=1,
        criteria=[
            RubricCriterion(
                criterion_id="crit-a",
                description="resuelve ecuaciones lineales",
                weight=1.0,
                max_score=4.0,
                mastery_descriptions={level: level.value for level in MasteryLevel},
            )
        ],
    )


def make_standard() -> CurriculumStandard:
    return CurriculumStandard(
        country="cl",
        version="2026.1",
        competencies=[
            Competency(
                code="MAT.8.1",
                description="modela situaciones con expresiones algebraicas",
                grade_level="grade-8",
                subject="matematicas",
            )
        ],
    )


def write_defaults(staging: Path, subjects: list[str]) -> None:
    bindings = [
        {
            "subject": subject,
            "grade_level": "grade-8",
            "rubric": make_rubric().model_dump(mode="json"),
            "curriculum_standard": make_standard().model_dump(mode="json"),
        }
        for subject in subjects
    ]
    root = staging / BUCKET
    root.mkdir(parents=True, exist_ok=True)
    (root / "catalog-defaults.json").write_text(
        json.dumps({"bindings": bindings}), encoding="utf-8"
    )


def write_batch_files(staging: Path, names: tuple[str, ...]) -> None:
    root = staging / BUCKET / PREFIX
    root.mkdir(parents=True, exist_ok=True)
    for name in names:
        (root / name).write_bytes(b"scan-bytes")
