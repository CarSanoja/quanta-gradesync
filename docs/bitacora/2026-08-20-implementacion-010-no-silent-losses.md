# Dev log — Implementation 010: no silent losses

**Date:** 2026-08-20
**Domain:** Implementation
**Fulfills:** SOL-017 (fix round for adversarial-review findings F-04, F-16, F-27)
**Verification:** offline suite **290 passed / 6 skipped** (was 280/6; +10 scenario tests, zero existing expectations loosened); live GCP-mode run over the real 16-exam batch confirming the happy path (14 synced / 2 quarantined) with the new honest fields.

## The invariant installed

Every submission in a batch manifest now ends in exactly one visible terminal
state — synced, quarantined with a review item, or failed with a review item —
and nothing can shrink a batch's accounting denominator.

## F-04 — faithfulness verification is now three-state

`span_status()` returns verified / failed / **unchecked**; production telemetry
emits `evidence.span_verification` and no longer fabricates
`evidence.span_match = true` for a check that never ran (GCS batches carry no
transcripts). Confidence is not zeroed on absence — absence is not evidence of
hallucination — and every SIS ledger document now carries
`provenance.faithfulness_checked`, verified false on all 14 records of the live
run. Transcript-present behavior (fabricated quote → zero confidence →
quarantine) is unchanged and pinned by test.

## F-16 — crashed exams stay visible

`GradeGuard.grade()` returns an explicit outcome; a crash produces a
`SubmissionFailure` persisted in the session, a review item per failed student
("this exam could not be graded — it needs manual grading", translated on the
teacher surface), and the anomaly breaker now measures TWO classes — quarantine
ratio and failure ratio — both against the MANIFEST student count; either
suspends auto-sync. The adversarial scenario is a pinned test: 15 crashes + 1
clean → breaker trips, 15 failure items, goal not met; a retry that succeeds
resolves its item without duplicating (review ids are job:student). Known
residual: a batch where EVERY submission crashes still ends FAILED without
items (sync never runs); Pub/Sub redelivery remains the recovery path.

## F-27 — partial batches cannot report success

The verify stage re-lists the batch prefix once (local staging dir or GCS) and
diffs gradable objects against the manifest: missing files produce a
missing-files block on the verification report, one review item per file
("this scan arrived after grading started — it has not been graded"), and
`goal_met = false`. Listing failure degrades to `checked: false`, never
failing the job. Live: 16/16 objects matched against real GCS.

## Structure

grade_guard split (wiring, outcome), stages_sync split (sync_breaker,
incident_reviews), new batch_listing — every touched file within the 200-line
discipline.
