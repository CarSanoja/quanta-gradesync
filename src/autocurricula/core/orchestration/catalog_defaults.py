import json
import unicodedata

from pydantic import Field, ValidationError, model_validator

from autocurricula.core.orchestration.catalog import CatalogError
from autocurricula.schemas.common import StrictBaseModel
from autocurricula.schemas.curriculum import CurriculumStandard
from autocurricula.schemas.rubric import Rubric

SUBJECT_ALIASES = {
    "math": "matematicas",
    "maths": "matematicas",
    "mathematics": "matematicas",
    "matematica": "matematicas",
    "matematicas": "matematicas",
    "language": "lenguaje",
    "languagearts": "lenguaje",
    "lengua": "lenguaje",
    "castellano": "lenguaje",
    "science": "ciencias",
    "sciences": "ciencias",
    "ciencia": "ciencias",
}


def strip_accents(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value)
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def normalize_token(value: str) -> str:
    return strip_accents(value).strip().lower().replace(" ", "-")


def canonical_subject(value: str) -> str:
    normalized = normalize_token(value)
    return SUBJECT_ALIASES.get(normalized.replace("-", ""), normalized)


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
        wanted = canonical_subject(subject)
        for binding in self.bindings:
            if canonical_subject(binding.subject) == wanted:
                return binding
        known = ", ".join(sorted(binding.subject for binding in self.bindings))
        raise CatalogError(
            f"catalog defaults have no binding for subject {subject!r}; "
            f"this catalog binds: {known}"
        )


def parse_defaults(payload: str | bytes) -> CatalogDefaults:
    try:
        document = json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise CatalogError("catalog defaults are not valid json") from error
    try:
        return CatalogDefaults.model_validate(document)
    except ValidationError as error:
        raise CatalogError(f"catalog defaults failed schema validation: {error}") from error
