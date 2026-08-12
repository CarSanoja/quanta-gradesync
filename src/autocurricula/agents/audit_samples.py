from pathlib import Path

from autocurricula.config.settings import Settings, get_settings
from autocurricula.core.evolution.calibration_store import (
    CalibrationSample,
    CalibrationSet,
)
from autocurricula.schemas.grading import CriterionScore

AUDIT_CALIBRATION_DIR_NAME = "calibration_audits"
MAPPING_ITEM_MAX_SCORE = 1.0


def audit_calibration_dir(settings: Settings | None = None) -> Path:
    resolved = settings if settings is not None else get_settings()
    return resolved.local_data_dir / AUDIT_CALIBRATION_DIR_NAME


def load_audit_calibration(directory: Path | None = None) -> CalibrationSet:
    return CalibrationSet.from_directory(directory)


def build_audit_sample(
    submission_id: str,
    submission_summary: str,
    expected_mappings: dict[str, list[str]],
) -> CalibrationSet:
    items = sorted(
        f"{criterion_id}->{code}"
        for criterion_id, codes in expected_mappings.items()
        for code in codes
    )
    sample = CalibrationSample(
        submission_id=submission_id,
        submission_summary=submission_summary,
        criterion_ids=items,
        max_scores=[MAPPING_ITEM_MAX_SCORE for _ in items],
        expected=[
            CriterionScore(
                criterion_id=item,
                score=MAPPING_ITEM_MAX_SCORE,
                comment=f"human-verified mapping {item}",
                confidence=1.0,
            )
            for item in items
        ],
    )
    return CalibrationSet([sample])
