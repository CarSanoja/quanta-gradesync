# Dev log — Implementation 008: 16-student roster, executed resilience, real calibration, cold-start audit

**Date:** 2026-08-20
**Domain:** Implementation
**Fulfills:** SOL-015 (hackathon execution sprint, phase 3 — four parallel work streams)
**Verification:** offline suite **261 passed / 6 skipped** (was 258/6); measured evidence in `docs/reports/`.

## Demo roster (16 students)

Roster grew 8 → 16 (13 solid + wrong-math + illegible + injection): quarantine
ratio 2/16 = 12.5 % sits under the 15 % breaker, so the happy path is now
demoable. The four named cases kept byte-identical images (camila-rios retains
her documented 0.191 legibility score); ground truth extended to 8 human-graded
students; batch uploaded as the new demo source (`demo-source/v2`). The upload
itself triggered the deployed pipeline: **14 auto-synced / 2 quarantined,
breaker untripped — the target demo outcome, already proven in production.**

## Resilience scenarios executed (T5)

Runbook: `docs/runbooks/resilience-demo.md`; evidence:
`docs/reports/resilience-2026-08-20.md`. Executed today: duplicate delivery on
the deployed service (zero side effects), SIS-down → dead-letter → **orphan-only
retry proven** (exactly the 2 rejected records written on the restored third
delivery), kill −9 mid-grade → checkpoint and grading results survived.
Findings: **F1 (real bug, fixed same day)** — the webhook treated any
non-failed checkpoint as processed, so a crash-killed job's redelivery was
acked as `duplicate` and the job could never resume; now stale in-progress
checkpoints (default > 600 s) accept redelivery and resume, fresh ones still
dedupe. F2 — a connection-level SIS outage fails the sync stage (5xx → retry
path) rather than parking per-record dead-letter entries; documented semantics.
F3 — any bucket upload triggers the deployed pipeline, so local probes against
the shared bucket must budget for and clean up their deployed twins.

## Calibration against human graders (T6)

`scripts/run_calibration.py` ran the production grading evaluator (real page
images, gemini-3.5-flash) against the 4-student human ground truth, then a real
tournament (3 LLM-proposed candidates). Baseline: **MAE 0.208, QWK 0.845,
bias −0.042; 8/12 criterion scores match the human exactly.** No candidate beat
baseline — rejections logged with rationale, convergence stopped the loop, no
promotion: the honest outcome, and the demo story is "the system refuses
unproven prompt changes". Follow-up: candidates may embed ground-truth scores
in few-shots (leakage the anti-gaming validator does not yet inspect). Cost of
the full run: $0.63.

## Cold-start audit (task 18)

A fresh GitHub clone following the README literally did not finish: `uv` absent
with no fallback, `.env` placeholders contaminating the suite, and three
unstated prerequisites in the demo flow. README rewritten and re-audited: clean
clone → suite green → API up → real local demo run (7 synced, camila-rios
quarantined, approve → SIS) in ~5 minutes following only the docs.

## Process

Four parallel workflow agents on disjoint file sets; orchestrator reviewed,
committed (7 atomic commits incl. the F1 fix), and validated. Winner-benchmark
research recorded separately in `docs/reports/winner-benchmark.md`.
