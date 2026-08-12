import json

import pytest
from pydantic import ValidationError

from autocurricula.schemas.curriculum import CurriculumAuditResult
from autocurricula.schemas.grading import GradingResult
from autocurricula.schemas.risk import RiskAssessment

pytestmark = pytest.mark.calibration

GRADING_PAYLOAD = json.loads(
    """
    {
      "submission_id": "sub_001",
      "criterion_scores": [
        {
          "criterion_id": "ALG.1",
          "score": 4.0,
          "comment": "Flawless algebraic manipulation across Q1-Q3.",
          "confidence": 0.95,
          "evidence": [
            {
              "page": 1,
              "quote": "(x+3)(x-2) = x^2 + x - 6",
              "rationale": "Correct factoring verified on the scanned page."
            }
          ]
        },
        {
          "criterion_id": "GEO.2",
          "score": 3.5,
          "comment": "Sketch correct with labeled axes.",
          "confidence": 0.9
        }
      ],
      "total_score": 7.5,
      "percentage": 75.0,
      "feedback": "Strong command of quadratics; minor axis labeling slip."
    }
    """
)

CURRICULUM_PAYLOAD = json.loads(
    """
    {
      "submission_id": "sub_001",
      "mappings": {
        "ALG.1": ["M.8.2.1", "M.8.2.3"],
        "GEO.2": ["M.8.4.1"]
      },
      "covered_codes": ["M.8.2.1", "M.8.2.3", "M.8.4.1"],
      "missing_codes": ["M.8.3.2"],
      "notes": "Geometry reasoning partially evidenced; statistics competency untouched."
    }
    """
)

RISK_PAYLOAD = json.loads(
    """
    {
      "student_id": "stu_0142",
      "job_id": "job_2026_05_12_001",
      "risk_score": 0.72,
      "level": "high",
      "drivers": [
        {
          "metric": "avg_percentage",
          "value": 48.5,
          "threshold": 55.0,
          "explanation": "Term average sits below the pass band."
        },
        {
          "metric": "trend_slope",
          "value": -6.2,
          "threshold": -5.0,
          "explanation": "Three consecutive declining submissions."
        }
      ],
      "recommended_interventions": [
        "Schedule twice-weekly tutoring",
        "Notify guardian with progress packet"
      ],
      "assessed_at": "2026-05-12T08:30:00Z"
    }
    """
)


def test_grading_result_accepts_representative_payload():
    result = GradingResult.model_validate(GRADING_PAYLOAD)

    assert result.submission_id == "sub_001"
    assert result.total_score == pytest.approx(7.5)
    assert result.percentage == pytest.approx(75.0)
    assert result.criterion_scores[0].evidence[0].page == 1
    assert result.criterion_scores[1].evidence == []
    assert result.criterion_scores[0].confidence == pytest.approx(0.95)


def test_curriculum_audit_result_accepts_representative_payload():
    audit = CurriculumAuditResult.model_validate(CURRICULUM_PAYLOAD)

    assert audit.mappings["ALG.1"] == ["M.8.2.1", "M.8.2.3"]
    assert audit.covered_codes == ["M.8.2.1", "M.8.2.3", "M.8.4.1"]
    assert audit.missing_codes == ["M.8.3.2"]
    assert set(audit.covered_codes).isdisjoint(audit.missing_codes)


def test_risk_assessment_accepts_representative_payload():
    assessment = RiskAssessment.model_validate(RISK_PAYLOAD)

    assert assessment.student_id == "stu_0142"
    assert assessment.level.value == "high"
    assert assessment.risk_score == pytest.approx(0.72)
    assert assessment.drivers[0].metric == "avg_percentage"
    assert assessment.drivers[1].value == pytest.approx(-6.2)
    assert assessment.assessed_at.tzinfo is not None


def test_naive_timestamps_are_coerced_to_utc():
    payload = {**RISK_PAYLOAD, "assessed_at": "2026-05-12T08:30:00"}

    assessment = RiskAssessment.model_validate(payload)

    assert assessment.assessed_at.utcoffset().total_seconds() == 0


def test_extra_fields_are_rejected():
    with pytest.raises(ValidationError, match="Extra inputs"):
        GradingResult.model_validate(
            {**GRADING_PAYLOAD, "grader_name": "automated"}
        )
    with pytest.raises(ValidationError, match="Extra inputs"):
        CurriculumAuditResult.model_validate(
            {**CURRICULUM_PAYLOAD, "auditor_model": "gemini-3.5-flash"}
        )
    with pytest.raises(ValidationError, match="Extra inputs"):
        RiskAssessment.model_validate({**RISK_PAYLOAD, "model_id": "gemini-3.5-pro"})


def test_wrong_types_are_rejected():
    with pytest.raises(ValidationError):
        GradingResult.model_validate({**GRADING_PAYLOAD, "percentage": "seventy-five"})
    with pytest.raises(ValidationError):
        GradingResult.model_validate(
            {**GRADING_PAYLOAD, "criterion_scores": {"ALG.1": 4.0}}
        )
    with pytest.raises(ValidationError):
        CurriculumAuditResult.model_validate(
            {**CURRICULUM_PAYLOAD, "covered_codes": "M.8.2.1"}
        )
    with pytest.raises(ValidationError):
        RiskAssessment.model_validate({**RISK_PAYLOAD, "level": "severe"})
    with pytest.raises(ValidationError):
        RiskAssessment.model_validate({**RISK_PAYLOAD, "risk_score": "high"})


def test_semantic_constraints_are_enforced():
    duplicated = json.loads(json.dumps(GRADING_PAYLOAD))
    duplicated["criterion_scores"][1]["criterion_id"] = duplicated[
        "criterion_scores"
    ][0]["criterion_id"]
    with pytest.raises(ValidationError, match="criterion_id values must be unique"):
        GradingResult.model_validate(duplicated)

    with pytest.raises(ValidationError, match="cannot be both covered and missing"):
        CurriculumAuditResult.model_validate(
            {**CURRICULUM_PAYLOAD, "covered_codes": ["M.8.2.1", "M.8.3.2"]}
        )
    with pytest.raises(ValidationError):
        CurriculumAuditResult.model_validate(
            {**CURRICULUM_PAYLOAD, "missing_codes": ["M.8.3.2", "M.8.3.2"]}
        )

    with pytest.raises(ValidationError):
        RiskAssessment.model_validate({**RISK_PAYLOAD, "risk_score": 1.5})
    with pytest.raises(ValidationError):
        GradingResult.model_validate({**GRADING_PAYLOAD, "percentage": 150.0})
    with pytest.raises(ValidationError):
        GradingResult.model_validate(
            {key: value for key, value in GRADING_PAYLOAD.items() if key != "feedback"}
        )


def test_frozen_models_reject_mutation():
    result = GradingResult.model_validate(GRADING_PAYLOAD)
    audit = CurriculumAuditResult.model_validate(CURRICULUM_PAYLOAD)
    assessment = RiskAssessment.model_validate(RISK_PAYLOAD)

    with pytest.raises(ValidationError):
        result.submission_id = "sub_999"
    with pytest.raises(ValidationError):
        audit.notes = "rewritten"
    with pytest.raises(ValidationError):
        assessment.risk_score = 0.1
