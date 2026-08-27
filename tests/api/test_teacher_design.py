from pathlib import Path

import httpx
import pytest

from autocurricula.api.main import create_app

STATIC = Path("src/autocurricula/api/static")

STYLES = (
    "teacher.css",
    "teacher-screens.css",
    "teacher-review.css",
    "teacher-dialogs.css",
)

MODULES = (
    "teacher-batch.js",
    "teacher-rail.js",
    "teacher-roster.js",
    "teacher-intake.js",
    "teacher-staging.js",
    "teacher-marks.js",
    "teacher-routing.js",
)


def source(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


@pytest.fixture
def app():
    return create_app()


async def test_every_stylesheet_and_module_of_the_design_is_served(app) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        for name in STYLES:
            response = await client.get(f"/teacher/assets/{name}")
            assert response.status_code == 200, name
            assert response.headers["content-type"].startswith("text/css")
        for name in MODULES:
            response = await client.get(f"/teacher/assets/{name}")
            assert response.status_code == 200, name
            assert response.headers["content-type"].startswith("text/javascript")


def test_the_page_links_every_stylesheet_and_carries_the_rail() -> None:
    page = source("teacher.html")

    for name in STYLES:
        assert f"/teacher/assets/{name}" in page
    assert 'class="rail"' in page
    assert 'id="rail-label"' in page
    assert 'id="rail-mark"' in page
    assert 'id="nav-needs"' in page
    assert 'id="nav-resume"' in page
    assert 'class="grid-veil"' in page


def test_the_design_tokens_and_type_scale_are_the_ones_of_the_import() -> None:
    styles = source("teacher.css")

    assert "--ink: #0b0a09;" in styles
    assert "--paper: #f2ece1;" in styles
    assert "--amber: #ffb545;" in styles
    assert '"Instrument Serif"' in styles
    assert '"DM Sans"' in styles
    assert '"JetBrains Mono"' in styles
    assert "radial-gradient(120% 90% at 80% -10%" in styles
    assert "@keyframes gs-rise" in styles
    assert "@keyframes gs-pulse" in styles


def test_the_teacher_declares_the_assessment_before_dropping_anything() -> None:
    screens = source("teacher-screens.js")
    intake = source("teacher-intake.js")

    assert "lotFields(ctx)," in screens
    assert 'dropzone(ctx, "Drop the whole pile here"' in screens
    assert '["assessment", "Assessment name", "Midterm 1"],' in intake
    assert 'zone.addEventListener("drop"' in intake


def test_home_and_grades_both_list_every_batch_you_have_sent() -> None:
    screens = source("teacher-screens.js")

    assert "ctx.summary.batches.map" in screens
    assert "ctx.openBatch(batch.lot_code)" in screens
    assert 'recentBatches(ctx, "Batches you have sent")' in screens
    assert 'recentBatches(ctx, "Recent batches")' in screens


def test_the_batch_screen_counts_filters_and_groups_the_whole_roster() -> None:
    batch = source("teacher-batch.js")
    roster = source("teacher-roster.js")

    assert 'class: "counters"' in batch
    assert 'class: `filter${active === band.key ? " is-on" : ""}`' in batch
    assert 'label: "waiting for you", live: batch.waiting_for_you > 0' in batch
    assert "Nothing in this batch is in that state any more." in batch
    for key in ("judgement", "batch_hold", "failed", "grading", "gradebook", "decided"):
        assert f'key: "{key}"' in roster
    assert "String(index + 1).padStart(2, \"0\")" in roster


def test_the_batch_filter_is_an_address_you_can_share() -> None:
    routing = source("teacher-routing.js")
    state = source("teacher-state.js")

    assert 'url.searchParams.set("show", state.queries.band)' in routing
    assert 'state.queries.band = route.get("show") || "";' in routing
    assert 'band: initialRoute.get("show") || "",' in state


def test_the_rail_carries_the_screen_and_the_work_waiting_for_you() -> None:
    rail = source("teacher-rail.js")
    teacher = source("teacher.js")

    assert 'home: "Send scans",' in rail
    assert "dom.bell.classList.toggle(\"is-quiet\", waiting < 1);" in rail
    assert "paintRail(screen, waiting);" in teacher
    assert "paintResume(" in teacher
    assert "setupRail({" in teacher


def test_new_work_announces_itself_with_something_you_can_click() -> None:
    dialogs = source("teacher-dialogs.js")
    teacher = source("teacher.js")

    assert "toastOpenAction = options.onOpen || null;" in dialogs
    assert "dom.toastActions.hidden = !toastOpenAction;" in dialogs
    assert "function announceWork(waiting)" in teacher
    assert 'openLabel: "Open them",' in teacher


def test_the_exam_page_shows_the_reading_behind_every_criterion() -> None:
    marks = source("teacher-marks.js")
    review = source("teacher-review.js")

    assert "criterion.evidence || []" in marks
    assert "what the student wrote" in marks
    assert 'criterion.confidence_band' in marks
    assert 'class: "review-figures"' in review
    assert "confidenceBand(review.confidence_band)" in review
    assert "ctx.restHeld > 0" in review
    assert "ctx.onApplyRest()" in review


def test_the_grader_confidence_reaches_the_teacher_as_words_not_a_model_number() -> None:
    marks = source("teacher-marks.js")

    assert 'high: { word: "sure of this reading"' in marks
    assert 'low: { word: "not sure of this reading"' in marks
    assert "Math.round(confidence * 100)" not in marks


def test_the_sending_screen_shows_each_file_moving_through_its_stages() -> None:
    uploading = source("teacher-uploading.js")

    assert 'const STAGES = ["named", "sending", "arrived"];' in uploading
    assert 'class: "pipe-pct"' in uploading
    assert 'class: `file-dot${tone}`' in uploading
    assert 'el("h2", { class: "section-title", text: "File by file" })' in uploading
