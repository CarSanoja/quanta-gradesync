from typing import Self

from pydantic import Field, field_validator, model_validator

from autocurricula.schemas.common import FrozenStrictModel


class Competency(FrozenStrictModel):
    code: str = Field(min_length=1)
    description: str = Field(min_length=1)
    grade_level: str = Field(min_length=1)
    subject: str = Field(min_length=1)


class CurriculumStandard(FrozenStrictModel):
    country: str = Field(min_length=1)
    version: str = Field(min_length=1)
    competencies: list[Competency] = Field(min_length=1)

    @field_validator("competencies")
    @classmethod
    def _unique_codes(cls, value: list[Competency]) -> list[Competency]:
        codes = [competency.code for competency in value]
        if len(codes) != len(set(codes)):
            raise ValueError("competency codes must be unique within a curriculum standard")
        return value


class CurriculumAuditResult(FrozenStrictModel):
    submission_id: str = Field(min_length=1)
    mappings: dict[str, list[str]] = Field(default_factory=dict)
    covered_codes: list[str] = Field(default_factory=list)
    missing_codes: list[str] = Field(default_factory=list)
    notes: str = ""

    @field_validator("covered_codes", "missing_codes")
    @classmethod
    def _unique_codes(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("code lists must not contain duplicates")
        return value

    @model_validator(mode="after")
    def _disjoint_codes(self) -> Self:
        overlap = set(self.covered_codes) & set(self.missing_codes)
        if overlap:
            raise ValueError(f"codes cannot be both covered and missing: {sorted(overlap)}")
        return self
