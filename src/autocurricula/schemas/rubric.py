from enum import StrEnum

from pydantic import Field, field_validator

from autocurricula.schemas.common import FrozenStrictModel


class MasteryLevel(StrEnum):
    NO_EVIDENCE = "no_evidence"
    DEVELOPING = "developing"
    PROFICIENT = "proficient"
    ADVANCED = "advanced"


class RubricCriterion(FrozenStrictModel):
    criterion_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    weight: float = Field(gt=0)
    max_score: float = Field(gt=0)
    mastery_descriptions: dict[MasteryLevel, str] = Field(min_length=1)

    @field_validator("mastery_descriptions")
    @classmethod
    def _complete_mastery_descriptions(
        cls, value: dict[MasteryLevel, str]
    ) -> dict[MasteryLevel, str]:
        missing = [level.value for level in MasteryLevel if level not in value]
        if missing:
            raise ValueError(f"missing mastery descriptions for levels: {missing}")
        return value


class Rubric(FrozenStrictModel):
    rubric_id: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    version: int = Field(ge=1)
    criteria: list[RubricCriterion] = Field(min_length=1)

    @field_validator("criteria")
    @classmethod
    def _unique_criterion_ids(cls, value: list[RubricCriterion]) -> list[RubricCriterion]:
        ids = [criterion.criterion_id for criterion in value]
        if len(ids) != len(set(ids)):
            raise ValueError("criterion_id values must be unique within a rubric")
        return value
