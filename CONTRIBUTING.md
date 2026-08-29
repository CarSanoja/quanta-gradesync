# Contributing

This is a hackathon submission that we intend to keep working on. Issues and
pull requests are welcome; there is no SLA.

## Getting it running

Everything you need is in the README: [local-mode
quickstart](README.md#local-mode-quickstart) takes a folder of generated exams
through grading, quarantine and human approval without leaving localhost, and
without a Google Cloud account.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q          # 850 passed, 10 skipped — offline, no credentials
```

The suite ignores any `.env` in the working directory, so it gives the same
result before and after you create one. The ten skips are `tests/live/`, which
need `GRADESYNC_LIVE_TESTS=1` and real credentials.

## What we look for in a change

**A test that would have failed before it.** The suite is the argument this
project makes about itself, so a change to behaviour arrives with a test that
exercises it. Prefer driving the real code path over asserting that a string
appears in a source file — we have some of the latter and are not proud of them.

**Comments that say why, not what.** The code says what it does. A comment earns
its place by recording the thing that is not visible: the failure that motivated
the shape, the constraint that rules out the obvious alternative.

**Claims backed by something a reader can check.** If a change adds a number to
the README, it also adds the artifact the number came from. `docs/reports/`
holds captured output, not prose — that is the standard.

## Before opening a pull request

```bash
pytest -q
ruff check src tests scripts
```

Ruff carries a known baseline of style findings (line lengths and modern-syntax
suggestions) that CI does not gate on. Do not let it grow; fixing some while you
are in a file is welcome.

## Reporting a vulnerability

See [SECURITY.md](SECURITY.md).
