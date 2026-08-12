import json
from pathlib import Path
from collections.abc import Callable

import pytest

from autocurricula.config.settings import Settings
from autocurricula.core.evolution import calibration_store
from autocurricula.core.evolution.calibration_store import (
    CalibrationSample,
    CalibrationSet,
)
from autocurricula.core.memory.manager import MemoryManager
from autocurricula.schemas.grading import CriterionScore, GradingResult

FIXTURES_DIR = Path(__file__).parent / "calibration" / "fixtures"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        local_mode=True,
        gcp_project_id="",
        local_data_dir=tmp_path / "local_data",
        gcs_local_staging_dir=tmp_path / "staging",
        sis_base_url="http://sis.example.test/api/v1",
        sis_api_token="calibration-test-token",
    )


@pytest.fixture
def memory_manager(settings: Settings) -> MemoryManager:
    return MemoryManager.from_settings(settings)


@pytest.fixture
def calibration_dir(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = settings.local_data_dir / "calibration"
    directory.mkdir(parents=True, exist_ok=True)
    for source in sorted(FIXTURES_DIR.glob("*.json")):
        payload = json.loads(source.read_text(encoding="utf-8"))
        target = directory / source.name
        target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    monkeypatch.setattr(calibration_store, "get_settings", lambda: settings)
    return directory


@pytest.fixture
def calibration_set(calibration_dir: Path) -> CalibrationSet:
    return CalibrationSet.from_directory(calibration_dir)


@pytest.fixture
def make_calibration_sample() -> Callable[..., CalibrationSample]:
    def _make(
        submission_id: str,
        expected_scores: dict[str, float],
        ceilings: dict[str, float],
        summary: str = "Handwritten exam scanned as JPEG pages with legible cursive.",
    ) -> CalibrationSample:
        criterion_ids = list(ceilings)
        expected = [
            CriterionScore(
                criterion_id=criterion_id,
                score=score,
                comment=f"Human ground-truth score for {criterion_id}",
                confidence=0.95,
            )
            for criterion_id, score in expected_scores.items()
        ]
        return CalibrationSample(
            submission_id=submission_id,
            submission_summary=summary,
            criterion_ids=criterion_ids,
            max_scores=[ceilings[criterion_id] for criterion_id in criterion_ids],
            expected=expected,
        )

    return _make


@pytest.fixture
def make_grading_result() -> Callable[..., GradingResult]:
    def _make(
        submission_id: str,
        scores: dict[str, float],
        ceilings: dict[str, float],
        feedback: str = "Scored against the published rubric.",
        confidence: float = 0.9,
    ) -> GradingResult:
        criterion_scores = [
            CriterionScore(
                criterion_id=criterion_id,
                score=score,
                comment=f"Criterion {criterion_id} assessed with page evidence.",
                confidence=confidence,
            )
            for criterion_id, score in scores.items()
        ]
        total = sum(scores.values())
        percentage = 100.0 * total / sum(ceilings.values())
        return GradingResult(
            submission_id=submission_id,
            criterion_scores=criterion_scores,
            total_score=round(total, 6),
            percentage=round(percentage, 6),
            feedback=feedback,
        )

    return _make
