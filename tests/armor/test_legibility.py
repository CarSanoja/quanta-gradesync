from pathlib import Path

import pytest

from autocurricula.core.armor import (
    DEFAULT_FULL_TRUST_LEGIBILITY,
    batch_legibility,
    confidence_factor,
    legibility_score,
)
from tests.armor.fixtures import make_batch, make_submission, save_page


def test_degraded_scan_scores_below_sharp_scan(tmp_path: Path) -> None:
    sharp = legibility_score(save_page(tmp_path / "sharp.jpg"))
    degraded = legibility_score(save_page(tmp_path / "bad.jpg", blur=2.5, contrast=0.66))
    assert sharp is not None and degraded is not None
    assert degraded < sharp
    assert sharp >= DEFAULT_FULL_TRUST_LEGIBILITY
    assert degraded < 0.5


def test_metric_orders_by_degradation_level(tmp_path: Path) -> None:
    heavy = legibility_score(save_page(tmp_path / "heavy.jpg", blur=4.0, contrast=0.5))
    medium = legibility_score(save_page(tmp_path / "medium.jpg", blur=2.5, contrast=0.66))
    clean = legibility_score(save_page(tmp_path / "clean.jpg"))
    assert heavy < medium < clean


def test_unreadable_or_missing_file_yields_none(tmp_path: Path) -> None:
    garbage = tmp_path / "garbage.jpg"
    garbage.write_bytes(b"scan")
    assert legibility_score(garbage) is None
    assert legibility_score(tmp_path / "missing.jpg") is None


def test_confidence_factor_full_trust_and_floor() -> None:
    assert confidence_factor(None) == 1.0
    assert confidence_factor(1.0) == 1.0
    assert confidence_factor(0.70) == 1.0
    assert confidence_factor(0.35) == pytest.approx(0.5)
    assert confidence_factor(0.10) == 0.5
    assert confidence_factor(0.0) == 0.5


def test_confidence_factor_custom_curve_is_linear_between_floor_and_trust() -> None:
    assert confidence_factor(0.4, full_trust=0.8, floor=0.25) == pytest.approx(0.5)
    assert confidence_factor(0.1, full_trust=0.8, floor=0.25) == 0.25
    with pytest.raises(ValueError):
        confidence_factor(0.5, full_trust=0.0)
    with pytest.raises(ValueError):
        confidence_factor(0.5, floor=1.5)


def test_batch_legibility_takes_worst_page_and_skips_unstaged(tmp_path: Path) -> None:
    sharp = save_page(tmp_path / "sharp.jpg")
    degraded = save_page(tmp_path / "degraded.jpg", blur=2.5, contrast=0.66)
    batch = make_batch(
        [
            make_submission("stu-clean", str(sharp)),
            make_submission("stu-blurry", str(degraded)),
            make_submission("stu-unstaged", None),
        ]
    )
    scores = batch_legibility(batch)
    assert set(scores) == {"stu-clean", "stu-blurry"}
    assert scores["stu-blurry"] < scores["stu-clean"]
