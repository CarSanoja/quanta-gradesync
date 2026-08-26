import pytest

from autocurricula.core.orchestration.catalog import CatalogError
from autocurricula.core.orchestration.catalog_defaults import (
    CatalogDefaults,
    canonical_subject,
)
from tests.orchestration.inference_fixtures import make_rubric, make_standard

SUBJECT = "Matematicas"


def defaults(*subjects: str) -> CatalogDefaults:
    bindings = [
        {
            "subject": subject,
            "grade_level": "grade-10",
            "rubric": make_rubric().model_dump(mode="json"),
            "curriculum_standard": make_standard().model_dump(mode="json"),
        }
        for subject in subjects
    ]
    return CatalogDefaults.model_validate({"bindings": bindings})


@pytest.mark.parametrize(
    "typed",
    ["Matematicas", "matematicas", "Matemáticas", "Mathematics", "maths", "MATH", " Math "],
)
def test_a_teacher_may_type_the_subject_in_her_own_words(typed: str) -> None:
    assert defaults(SUBJECT).binding_for(typed).subject == SUBJECT


def test_accents_and_case_never_decide_a_batch(typed: str = "MATEMÁTICAS") -> None:
    assert canonical_subject(typed) == canonical_subject("matematicas")


def test_a_subject_the_school_never_configured_is_still_refused() -> None:
    with pytest.raises(CatalogError) as error:
        defaults(SUBJECT).binding_for("Historia")

    assert "this catalog binds: Matematicas" in str(error.value)


def test_the_error_names_every_subject_the_catalog_binds() -> None:
    catalog = defaults(SUBJECT, "Lenguaje")

    with pytest.raises(CatalogError) as error:
        catalog.binding_for("Astrophysics")

    assert "this catalog binds: Lenguaje, Matematicas" in str(error.value)


def test_the_manifest_accepts_a_rubric_whose_subject_is_spelled_differently() -> None:
    from autocurricula.core.orchestration.subjects import same_subject

    assert same_subject("Mathematics", "Matematicas")
    assert same_subject("Matemáticas", "matematicas")
    assert not same_subject("Historia", "Matematicas")
