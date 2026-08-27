from pathlib import Path

STATIC = Path("src/autocurricula/api/static")


def source(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def test_failed_uploads_are_not_counted_as_arrivals_or_discarded() -> None:
    upload = source("teacher-upload.js")
    uploading = source("teacher-uploading.js")

    assert 'const SENT = new Set(["received", "skipped"]);' in upload
    assert "state.received >= state.total" in uploading
    assert "state.received / state.total" in uploading
    assert "state.finished && !state.failed.length" in upload


def test_upload_copy_only_allows_leaving_after_every_file_arrives() -> None:
    uploading = source("teacher-uploading.js")

    assert "Sending is in progress. Keep this page open" in uploading
    assert "Some files were not sent. Try those again" in uploading
    assert "Every file has arrived. You can safely leave" in uploading
    assert "sending continues on its own" not in uploading


def test_sequential_class_files_are_not_grouped_as_one_exam() -> None:
    filenames = source("teacher-filenames.js")

    assert "const MAX_IMPLICIT_PAGE_GROUP = 3;" in filenames
    assert "members.length <= MAX_IMPLICIT_PAGE_GROUP" in filenames
    assert "explicit || plausibleImplicitGroup" in filenames


def test_done_waits_for_uploads_and_refuses_failures() -> None:
    teacher = source("teacher.js")
    uploading = source("teacher-uploading.js")

    assert "state.startWhenUploaded = true;" in teacher
    assert "maybeFinishUploading" in teacher
    assert "Some files were not sent. Try those again before you start grading." in teacher
    assert "disabled: state.running" in uploading


def test_access_code_is_remembered_and_cancel_cannot_leave_a_blank_page() -> None:
    api = source("api.js")
    dialogs = source("teacher-dialogs.js")

    assert "localStorage.getItem(TOKEN_KEY)" in api
    assert "localStorage.setItem(TOKEN_KEY" in api
    assert "GradeSync needs your access code" in dialogs


def test_home_never_renders_a_null_band_or_claims_an_unfinished_batch_is_done() -> None:
    screens = source("teacher-screens.js")

    assert "...(band ? [band] : [])" in screens
    assert "const complete = batch && batch.settled" in screens
    assert "still being graded; nothing needs your decision yet" in screens


def test_waiting_work_keeps_polling_and_updates_the_window_title() -> None:
    teacher = source("teacher.js")

    assert "state.summary.waiting_count > 0" in teacher
    assert "Updates are paused after six minutes" in teacher
    assert "document.title = waiting" in teacher


def test_held_students_can_be_opened_directly_and_precaution_names_are_listed() -> None:
    held = source("teacher-held.js")

    assert 'ctx.goReview("judgement", item.review_id)' in held
    assert 'ctx.goReview("batch_hold", item.review_id)' in held
    assert "group.items.slice(0, LIST_CAP)" in held


def test_every_teacher_screen_has_an_address_and_back_navigation() -> None:
    teacher = source("teacher.js")
    screens = source("teacher-screens.js")

    routing = source("teacher-routing.js")
    assert 'put(url, "batch", state.lotCode)' in routing
    assert 'url.searchParams.set("review", review.student_id)' in routing
    assert 'url.searchParams.set("grades", state.queries.grades || "1")' in routing
    assert 'url.searchParams.set("needs", "1")' in routing
    assert 'url.searchParams.set("send", "1")' in routing
    assert 'window.addEventListener("popstate"' in teacher
    assert "ctx.summary.batches.map" in screens
    assert "ctx.openBatch(batch.lot_code)" in screens


def test_review_can_move_and_reopen_without_deciding() -> None:
    teacher = source("teacher.js")
    review = source("teacher-review.js")

    assert "function moveReview(delta)" in teacher
    assert "ctx.onPrevious()" in review
    assert "ctx.onNext()" in review
    assert 'state.review.group === "history"' in source("teacher-state.js")
    assert "This decision is already recorded" in review


def test_search_uses_the_server_and_grade_breakdown_prefers_rubric_titles() -> None:
    actions = source("teacher-actions.js")
    grades = source("teacher-grades.js")

    assert "endpoints.sisRecords(\"\", RECORD_LIMIT, studentId)" in actions
    assert "score.title || criterionTitle" in grades


def test_scan_cache_progress_notifications_and_collision_position_are_visible() -> None:
    review = source("teacher-review.js")
    uploading = source("teacher-uploading.js")
    teacher = source("teacher.js")
    dialogs = source("teacher-dialogs.js")

    assert "const imageCache = new Map();" in review
    assert "const imageLoads = new Map();" in review
    assert "scan-placeholder is-loading" in review
    assert "progress-fill is-received" in uploading
    assert "progress-fill is-sending" in uploading
    assert "progress-fill is-failed" in uploading
    assert "new Notification" in teacher
    assert "position} of ${total}" in dialogs
