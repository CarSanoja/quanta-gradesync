# Dev log — Implementation 009: teacher surface at scale, adversarial research review

**Date:** 2026-08-20
**Domain:** Implementation + research
**Fulfills:** SOL-016 (teacher-scale round and adversarial self-review)
**Verification:** offline suite **280 passed / 6 skipped** (was 274/6); live browser validation with a synthetic 150-file batch; deploys 10 and 11 verified in production.

## Teacher surface, from 16 exams to 150 (deploys 10-11)

Two rounds on `GET /teacher`. First round: filename guidance where mistakes
happen (the file stem IS the student id), client-side multi-page detection
("These look like pages of one exam" with the wrong-sync preview), derived-name
preview per row, collision help, and nine accessibility fixes (AA contrast,
dialog focus traps, error states). Second round, built for a 60-year-old
teacher with 150 students: names are assigned IN THE PAGE (camera filenames
like IMG_2831 gate only their own row, with a thumbnail of the scan to read the
name from), guided one-by-one review with progress and auto-advance, a batch
summary header with chips/filter/collapse/retry replacing 150 rows, post-upload
progress in teacher language served by `GET /teacher/summary?batch=` ("We
received 20 exams... 13 are already in the gradebook"), and search plus
assessment grouping over synced grades. `teacher.py` split into router +
`teacher_views.py`; upload lane extracted to `teacher-upload.js`. Ingest gained
rename-mode uploads for non-student-id filenames and the batch cap was
deliberately raised 40 → 200 (a 150-student class plus margin).

## Adversarial research review (docs only)

A senior-ML-researcher pass attacked the system's limits and rebuilt them as a
roadmap, grounded in the measured reports: `docs/architecture/limits-adversarial-review.md`
(38 findings, F-01..F-38, severity-ranked, each tagged MEASURED/CODE/UNMEASURED
with a concrete school failure), `docs/architecture/self-learning-fleet.md`
(nine blocks A-I forming a reflective plane: contending memories with evidence-
weighted decaying claims, review-as-active-learning, adversarial self-play,
evidence-coverage confidence, cross-model dissent, drift sentinels, label
economy, completeness ledger, version pinning — each with GCP mapping and cost
budgets derived from the measured $0.0391/exam), and `docs/benchmarks/gradesync-bench.md`
(T-CI / T-LIVE / T-RED tiers, a 13-class injection taxonomy, computed minimum
sample sizes for the promotion gate, hard gates like severe-error = 0).
`docs/product/product-overview.md` gained the two-surfaces section, a
sees/touches/never-sees persona matrix, and the staged roadmap in school
language.

## Findings that demand code, not documentation

The review surfaced five production-grade defects now on the fix queue:
**F-27** silent partial batches (a stalled upload can start grading a truncated
manifest and later files are acked as duplicates); **F-04** the faithfulness
verifier reports `evidence.span_match = True` in production despite never
running (no transcripts exist in GCP mode); **F-09/F-08** the promotion gate is
statistically empty at N=4 (computed CIs straddle both bars) and selects on its
own test set; **F-21/F-22/F-17/F-18** the human loop emits no labels and a
month-keyed profile snapshot lets a second assessment erase the first;
**F-16** a crashed exam vanishes from the breaker's denominator (15 crashes +
1 clean exam → ratio 0/1, no breaker, no review items).
