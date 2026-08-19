import pytest

from autocurricula.agents.curriculum_auditor import AdkCurriculumAuditor, build_curriculum_auditor
from autocurricula.config.settings import Settings
from autocurricula.schemas.curriculum import CurriculumAuditResult
from autocurricula.schemas.grading import CriterionScore, EvidenceSpan, GradingResult
from tests.live.exam_fixtures import (
    CRITERION_ID,
    SUBMISSION_ID,
    build_audit_context,
    build_standard,
)
from tests.live.guard import live_only

pytestmark = [pytest.mark.live, live_only]


def build_grading_result() -> GradingResult:
    evidence = EvidenceSpan(
        page=1,
        quote="x^2 + x - 6 = (x+3)(x-2)",
        rationale="The student factored the trinomial into the correct binomial pair.",
    )
    score = CriterionScore(
        criterion_id=CRITERION_ID,
        score=9.0,
        comment="Correct factoring with a verification step.",
        evidence=[evidence],
        confidence=0.9,
    )
    return GradingResult(
        submission_id=SUBMISSION_ID,
        criterion_scores=[score],
        total_score=9.0,
        percentage=90.0,
        feedback="Strong factoring; next step is stating the zero-product reasoning.",
    )


async def test_curriculum_auditor_returns_valid_mapping(live_settings: Settings) -> None:
    auditor = build_curriculum_auditor(live_settings)
    assert isinstance(auditor, AdkCurriculumAuditor)
    standard = build_standard()
    audit = await auditor.audit(build_grading_result(), standard, build_audit_context())
    assert isinstance(audit, CurriculumAuditResult)
    assert audit.submission_id == SUBMISSION_ID
    valid_codes = {competency.code for competency in standard.competencies}
    assert set(audit.covered_codes) <= valid_codes
    assert set(audit.missing_codes) <= valid_codes
    assert not set(audit.covered_codes) & set(audit.missing_codes)
    assert set(audit.mappings) <= {CRITERION_ID}
    assert audit.covered_codes
