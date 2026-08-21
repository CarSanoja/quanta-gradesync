# Dev log — Implementation 012: repaying measured technical debt

**Date:** 2026-08-21
**Domain:** Implementation
**Fulfills:** SOL-019 (close the debts the system measured against itself)
**Verification:** offline suite **420 passed / 8 skipped** (was 347/8; +73 tests across three parallel work streams). No existing assertion was loosened.

Every debt in this cycle came from our own instrumentation — the red-team
campaign, the resilience runbook and the adversarial review — not from
speculation.

## Armor: the metadata channel and encoded payloads

The campaign scored A8 (metadata) 0/2 and A6 (obfuscated) 1/2 because the
screener only reads page images, while the manifest carried the object path
into the grading prompt. Now three layers: the upload API rejects a
grader-directed file stem (422 with a rename instruction); the bucket-drop path
— which cannot reject without losing a student's exam — sanitises instead,
deriving `redacted-<digest>` ids while `gcs_uri` keeps the real object name; and
at grade time every manifest-derived string is screened deterministically and
sanitised at the prompt boundary. Normalisation covers separators, camelCase,
NFKC, invisible characters, homoglyphs, leetspeak, reversal and base64.

Measured offline, model-free, reproducible without credentials: **A8 0/2 → 2/2,
A6 0/2 → 2/2**, total hostile 3/24 → 7/24, false positives on innocent controls
0/2 in both runs. Those four catches cost zero model calls and hold during a
Vertex outage. The live LLM campaign is an explicit re-runnable step
(`docs/reports/armor-metadata-channel-2026-08-21.md`); a run whose screen
fail-opens now carries `measurement_valid: false` and an INVALID RUN banner so
it can never be mistaken for a measurement.

**Blast-radius warning for future maintainers:** `INJECTION_PATTERNS` now backs
three surfaces — page screen, metadata channel and encoded prescreen. Widening
one regex widens three false-positive surfaces at once.

## Resilience: outage parity and the all-crash batch

A connection-level SIS outage raised `SisWriteError` and failed the sync stage
without parking a single dead-letter entry — the more likely real-world failure
bypassed the mechanism built for it. `write_with_rollback` now parks every
record it was carrying and raises `SyncOutageError`, so the documented
orphan-only retry applies verbatim on redelivery. Two deliberate asymmetries:
an outage does not increment `attempts` (otherwise three unlucky deliveries
would abandon a whole batch — worse than the bug), and records the SIS did
accept are resolved even when the same write partially failed.

The all-crash batch no longer dies silently: the sync stage tolerates zero
successful records, so every submission gets a failure review item and the
teacher sees cards instead of nothing.

## Human loop: decisions become labels, profiles stop eating themselves

`POST /review/{id}/override` accepts corrected per-criterion scores validated
against rubric maxima, writes the corrected record to the SIS and moves the item
to `overridden`. Approve, dismiss and override now each emit a durable label
(human decision, the model proposal it replaced, prompt version, timestamp)
readable through `GET /labels`, and the calibration loader can consume them —
the path out of the N=4 starvation documented in the calibration report.

Profile integrity: per-assessment facts are append-only and idempotent on
redelivery, and the term aggregate is a recomputed projection over them, so a
second assessment in the same calendar month no longer erases the first and a
later batch cannot wipe a human approval.

## Process note

Three agents worked disjoint subsystems in one tree. Two foreign edits landed
inside armor despite explicit exclusions: a regex change (good — it removed a
documented false positive, and was kept) and a test appended without its
imports, which broke collection for minutes. The owning agent restored green
with the minimum change and kept the intruding work rather than reverting it.
Workflow-spawned agents are not addressable mid-flight, so ownership conflicts
in that mode can only be reconciled at review time; named agents remain the
option when live intervention may be needed.
