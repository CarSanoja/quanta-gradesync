from pathlib import Path

STATIC = Path("src/autocurricula/api/static")


def test_the_jobs_timeline_refreshes_itself_while_a_batch_runs() -> None:
    poller = (STATIC / "console-jobs-poll.js").read_text(encoding="utf-8")

    assert "createJobsPoller" in poller
    assert "isTerminal" in poller
    assert "IDLE_POLLS_BEFORE_REST" in poller


def test_the_console_starts_it_only_on_that_view() -> None:
    console = (STATIC / "console.js").read_text(encoding="utf-8")

    assert 'view === "jobs" ? jobsPoller.start() : jobsPoller.stop();' in console


def test_the_view_shows_whether_it_is_live() -> None:
    page = (STATIC / "console.html").read_text(encoding="utf-8")
    dom = (STATIC / "console-dom.js").read_text(encoding="utf-8")

    assert 'id="jobs-poll"' in page
    assert 'jobsPoll: "jobs-poll"' in dom
