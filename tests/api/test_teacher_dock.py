from pathlib import Path

import httpx
import pytest

from autocurricula.api.main import create_app

STATIC = Path("src/autocurricula/api/static")


def source(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


@pytest.fixture
def app():
    return create_app()


async def test_the_dock_module_is_served(app) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/teacher/assets/teacher-dock.js")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/javascript")


def test_sending_no_longer_takes_over_the_page() -> None:
    """Three sections meant finishing one, navigating back, and starting again.

    The page now only takes over when the queue genuinely cannot continue without
    an answer — the same rule the rest of the product follows.
    """
    teacher = source("teacher.js")

    assert "function uploadNeedsHer()" in teacher
    assert "if (uploadNeedsHer() && !state.uploadDismissed" in teacher
    assert "if (uploadState().total && !state.uploadDismissed" not in teacher


def test_the_dock_survives_every_screen_change() -> None:
    """Inside the screen host it would be cleared on each render."""
    page = source("teacher.html")
    teacher = source("teacher.js")

    assert '<aside class="dock" id="upload-dock"' in page
    assert '<main id="screen" tabindex="-1"></main>' in page
    assert page.index('<main id="screen"') < page.index('id="upload-dock"')
    # painted on the ordinary path and on the review path, which returns early
    assert teacher.count("paintDock(dockHost, openBatch);") == 2


def test_each_batch_is_remembered_after_its_queue_is_cleared() -> None:
    """rows is the queue for one batch and gets emptied between them.

    Without a separate record a finished section would vanish from the page and
    she could not reach its grades without leaving — which is the thing this
    change exists to avoid.
    """
    upload = source("teacher-upload.js")

    assert "batches: []," in upload
    assert "function batchFor(lotCode)" in upload
    assert "uploads.batches.push(batch);" in upload
    assert "batch.done = true;" in upload


def test_a_clean_queue_clears_itself_so_the_next_pile_can_land() -> None:
    upload = source("teacher-upload.js")

    assert 'const UNRESOLVED = new Set(["failed", "needs-name", "held", "paused"]);' in upload
    assert "if (!uploads.rows.some((row) => UNRESOLVED.has(row.state))) {" in upload
    assert "uploads.rows.length = 0;" in upload


def test_the_grading_button_lives_on_the_batch_it_belongs_to() -> None:
    """It used to sit at the bottom of a screen that took over the page.

    Per batch, it also survives three sections at once — the old handler only
    knew about whichever queue was moving.
    """
    dock = source("teacher-dock.js")

    assert '"Done — start grading"' in dock
    assert "disabled: batch.running," in dock
    assert "`Sending ${batch.received} of ${batch.total}…`" in dock
    assert "onclick: () => onOpen(batch.lotCode)," in dock


def test_progress_never_moves_her_off_the_drop_zone() -> None:
    """Dropping a pile before filling the three fields took the page over.

    The drop zone already carries those fields, so there is nothing to take her
    to — and a loading animation is not a question.
    """
    teacher = source("teacher.js")

    assert "|| counts.awaitingLot;" not in teacher
    assert "counts.failed.length > 0;" in teacher


def test_the_dock_tells_her_she_can_keep_going() -> None:
    dock = source("teacher-dock.js")

    assert "You can drop the next section now." in dock
    assert "Drop the next section whenever you like" in dock


def test_the_dock_does_not_squeeze_the_dropzone_on_a_narrow_window() -> None:
    styles = source("teacher-screens.css")

    assert ".work { display: flex; align-items: flex-start; gap: 0; }" in styles
    assert "@media (max-width: 60rem) {" in styles
    assert "  .work { display: block; }" in styles
