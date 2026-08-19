from pydantic import BaseModel, Field

from autocurricula.schemas.curriculum import CurriculumAuditResult


class CriterionCompetencyMapping(BaseModel):
    criterion_id: str = Field(min_length=1)
    competency_codes: list[str] = Field(default_factory=list)


class AuditResponse(BaseModel):
    submission_id: str = Field(min_length=1)
    mappings: list[CriterionCompetencyMapping] = Field(default_factory=list)
    notes: str = ""

    def to_audit_result(self) -> CurriculumAuditResult:
        mappings = {
            mapping.criterion_id: sorted(set(mapping.competency_codes))
            for mapping in self.mappings
            if mapping.competency_codes
        }
        covered = sorted({code for codes in mappings.values() for code in codes})
        return CurriculumAuditResult(
            submission_id=self.submission_id,
            mappings=mappings,
            covered_codes=covered,
            missing_codes=[],
            notes=self.notes,
        )
