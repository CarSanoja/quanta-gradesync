import sys
import tempfile
from pathlib import Path

from autocurricula.core.armor import confidence_factor, legibility_score

REPO = Path(__file__).resolve().parents[2]
LOT = "2026_Matematicas_10A_Parcial1"
COMMITTED = REPO / ".local_data" / "sample_batch" / "batches" / LOT


def _generated_batch() -> Path:
    """Render the reference batch instead of skipping when it is not on disk.

    .local_data is gitignored, so on a clean clone these were the only tests that
    skipped — and the README promised a count that a clone could not produce.

    The thresholds hold across both rendering paths: macOS renders these pages
    with real TrueType handwriting fonts and Linux CI with Pillow's bundled
    default, and the same absolute cutoffs pass on both. The margin is why —
    degraded scores below 0.30, everything else above 0.90.
    """
    if COMMITTED.is_dir():
        return COMMITTED
    scripts = REPO / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    import generate_sample_batch as generator

    target = Path(tempfile.mkdtemp(prefix="gradesync-reference-")) / "sample_batch"
    generator.generate("reference", target, 20260819, 84)
    return target.resolve() / "batches" / LOT


SAMPLE_BATCH = _generated_batch()
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
