import json

from pydantic import Field, ValidationError, model_validator

from autocurricula.core.orchestration.catalog import CatalogError
from autocurricula.schemas.common import StrictBaseModel
from autocurricula.schemas.curriculum import CurriculumStandard
from autocurricula.schemas.rubric import Rubric


def normalize_token(value: str) -> str:
    return value.strip().lower().replace(" ", "-")


class CatalogDefaults(StrictBaseModel):
    class SubjectBinding(StrictBaseModel):
        subject: str = Field(min_length=1)
        grade_level: str = Field(min_length=1)
        rubric: Rubric
        curriculum_standard: CurriculumStandard

    bindings: list[SubjectBinding] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_subjects(self) -> "CatalogDefaults":
        subjects = [binding.subject for binding in self.bindings]
        if len(subjects) != len(set(subjects)):
            raise ValueError("subject bindings must be unique")
        return self

    def binding_for(self, subject: str) -> SubjectBinding:
        normalized = normalize_token(subject)
        for binding in self.bindings:
            if normalize_token(binding.subject) == normalized:
                return binding
        raise CatalogError(f"catalog defaults have no binding for subject {subject!r}")


def parse_defaults(payload: str | bytes) -> CatalogDefaults:
    try:
        document = json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise CatalogError("catalog defaults are not valid json") from error
    try:
        return CatalogDefaults.model_validate(document)
    except ValidationError as error:
        raise CatalogError(f"catalog defaults failed schema validation: {error}") from error
