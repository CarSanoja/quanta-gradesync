from pathlib import Path

import pytest

from autocurricula.core.armor import confidence_factor, legibility_score

SAMPLE_BATCH = (
    Path(__file__).resolve().parents[2]
    / ".local_data"
    / "sample_batch"
    / "batches"
    / "2026_Matematicas_10A_Parcial1"
)
DEGRADED_STUDENT = "camila-rios"
SOLID_STUDENTS = (
    "ana-torres",
    "andres-molina",
    "camilo-fuentes",
    "daniela-osorio",
    "gabriela-mendez",
    "isabela-cardenas",
    "lucia-navarro",
    "mateo-quintero",
    "nicolas-serrano",
    "renata-aguilar",
    "santiago-herrera",
    "sebastian-rincon",
    "valentina-suarez",
)
GRADED_NOT_SOLID = ("tomas-vega", "julian-pardo")
OBSERVED_MIN_MODEL_CONFIDENCE = 0.95
CONFIDENCE_THRESHOLD = 0.85

pytestmark = pytest.mark.skipif(
    not SAMPLE_BATCH.is_dir(),
    reason=(
        "sample batch missing; regenerate with scripts/generate_sample_batch.py "
        "--target .local_data/sample_batch --seed 20260819"
    ),
)


def score_of(student: str) -> float:
    value = legibility_score(SAMPLE_BATCH / f"{student}.jpg")
    assert value is not None
    return value


def test_degraded_scan_scores_clearly_below_every_other_page() -> None:
    degraded = score_of(DEGRADED_STUDENT)
    others = {
        student: score_of(student) for student in SOLID_STUDENTS + GRADED_NOT_SOLID
    }
    assert degraded <= 0.30
    assert all(score >= 0.90 for score in others.values()), others
    assert degraded < 0.5 * min(others.values())


def test_solid_scans_keep_effective_confidence_above_gate() -> None:
    for student in SOLID_STUDENTS + GRADED_NOT_SOLID:
        factor = confidence_factor(score_of(student))
        assert factor == 1.0
        assert OBSERVED_MIN_MODEL_CONFIDENCE * factor >= CONFIDENCE_THRESHOLD


def test_degraded_scan_falls_below_gate_despite_high_model_confidence() -> None:
    factor = confidence_factor(score_of(DEGRADED_STUDENT))
    assert factor < 1.0
    assert 0.98 * factor < CONFIDENCE_THRESHOLD
