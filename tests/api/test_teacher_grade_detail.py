from pathlib import Path

STATIC = Path("src/autocurricula/api/static")


def test_a_grade_row_opens_its_own_breakdown() -> None:
    grades = (STATIC / "teacher-grades.js").read_text(encoding="utf-8")

    assert 'type: "button"' in grades
    assert '"aria-expanded"' in grades
    assert "How this grade was made up" in grades
    assert "See the detail" in grades and "Hide the detail" in grades


def test_the_grades_screen_drives_that_row() -> None:
    screens = (STATIC / "teacher-screens.js").read_text(encoding="utf-8")

    assert "openGradeId(ctx.queries)" in screens
    assert "ctx.setQuery(openGradeKey(), next)" in screens


def test_the_open_row_survives_a_refresh() -> None:
    state = (STATIC / "teacher-state.js").read_text(encoding="utf-8")

    assert "open_grade" in state
