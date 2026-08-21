# Sync failure modes — outage parity and the zero-grade batch

| | |
|---|---|
| **Status** | Shipped behaviour, offline-measured (no cloud run was made for this note) |
| **Date** | 2026-08-21 |
| **Closes** | [F-34](limits-adversarial-review.md) / F2 of the [resilience report](../reports/resilience-2026-08-20.md); the all-submissions-crash residual of F-16 |
| **Code** | `core/resilience/{orphan_ledger,state_rollback}.py`, `core/orchestration/{stages_assessment,verifier,rework_loop}.py`, `schemas/{sis_sync,grading}.py` |
| **Tests** | `tests/resilience/test_sis_outage.py`, `tests/orchestration/test_failed_submissions.py` |

---

## 1. A connection-level outage now parks orphans like a rejection does

**Before.** `HttpSISConnector.write_grades` raises `SisWriteError` after three
connection attempts. `write_with_rollback` only wrote dead-letter entries for
per-record non-success statuses returned by a *responsive* SIS, so a total
outage — the likelier real-world failure — failed the sync stage with an empty
DLQ. Delivery 1 of `t5-sisdown-2026-08-20` measured exactly that.

**Now.** The connector error is caught in `write_with_rollback`, every record it
was carrying is parked as a `sis_write` dead-letter entry with reason
`sis unreachable before any record-level verdict: <error>`, the merged stage
result records each of them as `error:sis_unreachable`, and the stage still
fails with `SyncOutageError` so Pub/Sub redelivers. On redelivery the existing
orphan-only retry path applies unchanged.

Two deliberate asymmetries between an outage and a rejection:

- **An outage does not increment `attempts`.** `attempts` counts record-level
  verdicts, i.e. times the SIS looked at the record and refused it. Incrementing
  on outages would make three unlucky deliveries exhaust the whole batch and
  abandon every student silently — strictly worse than the bug being fixed. A
  newly parked outage orphan carries `attempts: 0`; a later rejection of the
  same record moves it to 1, and three rejections still exhaust it.
- **Records the SIS accepted are now resolved even when the same write
  partially failed.** Previously the resolve loop only ran on the fully clean
  path, so a partial failure left succeeded targets parked as pending orphans.
  That was harmless while outages produced no entries at all; with outage parity
  it would have made the next delivery re-post records the SIS already holds.

### Measured, offline (`tests/resilience/test_sis_outage.py`, one job, three deliveries)

| Delivery | SIS state | Job stage | Posted to SIS | DLQ pending after | SIS ledger |
|---|---|---|---|---|---|
| 1 | dead (raises `SisWriteError`) | `failed` | all 6 | 6 × `attempts 0` | empty |
| 2 | up, rejects 2 of 6 | `failed` | all 6 | 2 × `attempts 1` | 4 records |
| 3 | restored | `completed` | **only the 2 orphans** | none | 6 records, each written once |

Delivery 1's job error reads
`SyncOutageError: sis unreachable (SisWriteError: ConnectError: All connection
attempts failed); 6 records parked as orphans: [...]`.

`LocalDeadLetterStore` now creates its data directory on write: with the fix,
the first thing that touches the local DLQ can be an outage, before any
component has created `local_data/`.

---

## 2. A batch where every exam crashes no longer ends in silence

**Before.** `build_grade_step` raised `StageExecutionError("no submissions could
be graded")` when no submission produced a result. The job ended `FAILED` at the
grade stage, sync never ran, no review item was created, and the teacher saw
nothing at all — the exact opposite of the partial-failure path, which creates a
`failed_grading` card per crashed exam.

**Now.** The grade stage logs the incident and completes with an empty result,
and the pipeline carries the batch to the surfaces it is supposed to reach:
audit and risk produce nothing, sync tolerates zero records
(`SISWriteRequest.records` and `GradingBatchResult.results` no longer carry
`min_length=1`; the write path already short-circuits on an empty record list,
so no empty request is ever POSTed), `enqueue_failure_reviews` creates one card
per submission, and `verify` writes the goal-not-met report.

**The job still ends `FAILED`, deliberately.** The alternative — completing with
everything in review — would ACK a batch in which nothing was graded and declare
success on it. Zero successes is a systemic signal (model outage, revoked
capability, quota), not a per-exam one, so the run is marked failed *after* the
teacher-visible bookkeeping is durable: review items are written by the review
store as they are created, and `JobRunner._fail` persists the session state, so
the verification report survives the failure. The failure is raised by `verify`,
the stage whose job is to decide whether the goal was met, and keeps the
existing error string so operations and the fleet enforcement test still read
`no submissions could be graded`.

Redelivery of such a job is cheap rather than costly: every completed stage is
checkpointed, so a retry re-runs sync and verify with zero LLM calls. It also
cannot re-grade (the grade stage is checkpointed `succeeded` with an empty
result), so recovery from a total grader outage is a re-run of the batch, not a
redelivery — see the residuals below.

### Measured, offline (16 exams, every one crashing)

```
stage: failed | error: StageExecutionError: stage verify: no submissions could be graded
pending review items: 16 (all failed_grading)  |  sis ledger: empty
verify.passed=False   submissions_graded 0/16   failed_submissions_resolved False (16 waiting)
```

---

## 3. Residuals this note does not close

- **A redelivery cannot re-grade a zero-grade job.** `stage_done` treats the
  checkpointed empty grade result as success. Making the retry productive needs
  either a re-grade trigger for empty results or an explicit re-run entry point.
- **Exhausted orphans still produce no review card.** After three rejections a
  record is abandoned and the next sync returns success without it. That is
  pre-existing behaviour, now more visible because outages populate the same
  ledger.
- **The console labels the students of a zero-grade job `quarantined`.**
  `api/job_views._sis_status` returns quarantined for any student missing from
  the sync statuses. The teacher-facing card is correct
  (`This exam could not be graded — it needs manual grading.`); only the
  operator table mislabels it.
