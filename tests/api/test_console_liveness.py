from pathlib import Path

STATIC = Path("src/autocurricula/api/static")


def source(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def test_a_running_batch_never_serves_a_cached_detail() -> None:
    """A student who synced must not still read as pending.

    The job list signature is `job_id:stage:updated_at`, and the checkpoint
    behind `updated_at` is written once per stage. A batch grades and syncs exam
    after exam inside a single stage, so the signature can sit still for minutes
    while the contents change underneath it. Caching the detail across that
    window froze the student table at whatever it showed when the stage opened.
    """
    console = source("console.js")

    assert "function stillRunning(jobId)" in console
    assert "if (!stillRunning(jobId) && state.jobCache.has(jobId))" in console
    assert "if (detail && !stillRunning(jobId))" in console


def test_the_unchanged_list_still_refreshes_the_running_batch() -> None:
    console = source("console.js")

    assert "const listUnchanged = signature === state.jobsSignature" in console
    assert "&& state.activeJobId;" in console
    assert "if (stillRunning(state.activeJobId)) {" in console
    assert "      await selectJob(state.activeJobId);" in console


def test_the_quarantine_queue_and_its_badge_follow_the_run() -> None:
    """The queue only grows while a batch runs, and it never polled at all.

    It is also the surface the rail badge and the header chip read from, so a
    stale queue meant a stale "something needs you" signal on every view.
    """
    console = source("console.js")

    assert "const reviewPoller = createJobsPoller({" in console
    assert "await reviewController.load();" in console
    assert console.count("reviewPoller.start();") >= 2


def test_liveness_does_not_depend_on_which_view_you_are_on() -> None:
    """state.jobs is what tells every poller whether work is in flight.

    Only the jobs view refreshed it, so starting a batch while watching Mission
    control left the list stale, the poller read "nothing running", and the
    rail badge went to sleep through the run it was meant to announce.
    """
    console = source("console.js")

    assert 'if (state.view !== "jobs") {' in console
    assert "      await loadJobs();" in console


def test_the_optimizer_is_read_when_it_is_opened() -> None:
    console = source("console.js")

    assert 'if (view === "optimizer") {' in console
    assert "    loadOptimizer();" in console


def test_every_live_surface_has_something_driving_it() -> None:
    """One assertion per console surface, so a new view cannot ship inert."""
    console = source("console.js")

    drivers = {
        "jobs list": "jobsPoller.start()",
        "job detail": "if (stillRunning(state.activeJobId)) {",
        "review queue": "reviewPoller.start();",
        "sis ledger": "sisController.start()",
        "mission control": "liveController.start()",
        "optimizer": "loadOptimizer();",
    }
    for surface, driver in drivers.items():
        assert driver in console, surface


def test_the_fleet_is_deliberately_static() -> None:
    """The registry is derived at boot from configuration.

    It cannot change without a deploy, so polling it would be noise. This test
    exists so that staying static is a decision on the record rather than an
    oversight someone repeats.
    """
    console = source("console.js")

    assert "loadFleet()" in console
    assert "fleetPoller" not in console
