from pathlib import Path

STATIC = Path("src/autocurricula/api/static")


def source(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def test_the_third_state_is_never_the_word_synced() -> None:
    """A grade the model has returned is not a grade the school has.

    Stage results are persisted when the stage closes; if the service died
    mid-stage the work would be redone. Calling it synced would claim a
    durability the system does not have, so the row says what is true.
    """
    progress = source("console-job-progress.js")

    assert '[PROGRESS_GRADED]: "graded · not written"' in progress
    assert '"synced"' not in progress


def test_progress_is_read_from_the_span_that_ends_per_exam() -> None:
    progress = source("console-job-progress.js")

    assert 'const GRADING_PREFIX = "Grading_";' in progress
    assert 'const TRANSCRIPTION_PREFIX = "EvidenceTranscription_";' in progress
    assert 'if (event.kind !== "span_end")' in progress


def test_a_row_the_checkpoint_has_already_decided_keeps_its_word() -> None:
    """The feed may only speak for rows still reading pending."""
    view = source("views-jobs.js")

    assert 'student.sis_status === "pending" ? progressFor(progress, student) : null' in view
    assert "if (!live) {" in view
    assert "return pill(student.sis_status, student.sis_status);" in view


def test_the_feed_is_only_read_while_the_batch_is_running() -> None:
    """A settled batch has an authoritative checkpoint; the feed adds nothing."""
    console = source("console.js")

    assert "async function liveProgressFor(jobId)" in console
    assert "if (!stillRunning(jobId)) {" in console
    assert "return null;" in console
    assert "progressFromEvents(" in console


def test_both_identifiers_are_tried_so_the_rows_line_up() -> None:
    """Rows key on submission_id; some spans are named for the student."""
    progress = source("console-job-progress.js")

    assert "progress.get(student.submission_id) || progress.get(student.student_id)" in progress


def test_the_detail_and_the_feed_are_fetched_together() -> None:
    """Two sequential awaits would show the table before the states arrive."""
    console = source("console.js")

    assert "const [detail, progress] = await Promise.all([" in console
    assert "renderJobDetail(dom.jobDetail, detail, openReviewFromJob, progress);" in console
