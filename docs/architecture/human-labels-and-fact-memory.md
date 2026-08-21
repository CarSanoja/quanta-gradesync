# Human labels and append-only fact memory (F-17 / F-18 / F-21)

Design note for the debt repaid on 2026-08-21. It covers two findings from
`limits-adversarial-review.md` that share one root cause: **the system threw
away the things it could not undo** — human decisions, and prior assessments.

---

## 1. F-21 — the review queue now produces labels

### 1.1 What existed

| Action | What the system learned |
|---|---|
| `approve` | The record was written and a percentage merged. No reviewer trace |
| `dismiss` | Nothing at all |
| correct the grade | Impossible — no endpoint existed |

The calibration set was therefore stuck at N=4 fixtures while production graded
dozens of exams (`calibration-2026-08-20.md` computes that ~29–53 human-graded
exams are needed before the promotion gate is statistically meaningful).

### 1.2 What exists now

```text
POST /review/{id}/approve  ─┐
POST /review/{id}/dismiss  ─┼─► ReviewService ─► Label  ─► labels store
POST /review/{id}/override ─┘        │                       (local dir | Firestore)
                                     │                            │
                                     ▼                            ▼
                            SIS corrected record        GET /labels?job_id=&limit=
                            + append-only fact                    │
                                                                  ▼
                                                    load_labelled_samples()
                                                    → list[CalibrationSample]
```

**The override.** `POST /review/{review_id}/override` takes corrected
per-criterion scores plus an optional note. Scores are validated against the
rubric maxima before anything is written; the corrected `SISGradeRecord` (with
recomputed total and percentage) goes to the SIS, the item moves to the new
terminal status `overridden`, and the corrected record and note are stored on
the item so the decision is auditable.

**Where the rubric maxima come from.** `ReviewItem` carries no rubric, so
`api/review_context.py` recovers them per request:

1. `checkpoint_store.get(job_id)` → `JobRecord.event`
2. `catalog.load_manifest(event)` → `rubric.criteria` → `{criterion_id: max_score}`
3. `checkpoint_store.load_state(job_id)` → the checkpointed `grade` stage result
   → the model's per-criterion proposal for this student

Both lookups are best-effort. When the manifest cannot be resolved the override
falls back to the **total** rubric ceiling derived from the proposal itself
(`100 × score / percentage`), which still rejects out-of-range corrections; when
even that is underivable (a zero-score incident placeholder) the override is
refused with 422 rather than writing an unvalidated grade.

**Label shape.** One `Label` per decision (not per criterion — the pragmatic
slice of block B in `self-learning-fleet.md`), carrying: student, job, subject,
decision type, per-criterion `machine_score` / `human_score` / `max_score`,
machine and human percentages, the prompt variant id and version SHA taken from
the record's provenance, the reviewer note, and a timestamp. `label_id` is
`{review_id}:{decision}`, so a redelivered decision overwrites rather than
duplicates.

| Decision | `human_score` | `human_percentage` | Usable as calibration ground truth |
|---|---|---|---|
| approve | = machine score (confirmed) | = machine percentage | yes |
| dismiss | `null` | `null` | no — deliberately excluded |
| override | teacher's corrected score | recomputed from the corrected total | yes |

**Storage duality.** `label_store_for(review_store)` derives the label store
from the review store, so labels always follow reviews: a `LocalReviewStore`
yields `<local_data_dir>/labels/*.json`, a `FirestoreReviewStore` yields the
`labels` collection on the same client. `build_label_store(settings)` is the
explicit settings-based equivalent for whoever wires the container next.

**Feeding calibration.** `core/evolution/calibration_labels.py` converts labels
into `CalibrationSample` objects (a criterion is usable only when it has both a
human score and a known ceiling) and exposes `load_labelled_samples(store, …)`
and `load_labelled_calibration_set(store, …)`. Promotion-gate statistics and the
optimizer are **not** touched — this only makes real teacher decisions available
where fixtures used to be the only source.

---

## 2. F-17 / F-18 — the profile no longer eats itself

### 2.1 What existed

`write_profiles` built a `TermSnapshot` from *this batch only* and replaced the
month's snapshot; `merge_student_percentage` (the approval path) incremented it.
Two writers, two meanings, and the replacing one ran last:

```text
Parcial 1 syncs           → term-2026-08: avg 82, count 1
Quarantined student ok'd  → term-2026-08: avg 79, count 2
Parcial 2 syncs           → term-2026-08: avg 61, count 1   ← both erased
```

### 2.2 What exists now

Per-assessment facts are **append-only** and the term is a **recomputed
projection** over them:

```text
AssessmentFact(fact_id = "{job_id}::{student_id}")
   student_id, job_id, term, avg_percentage, submissions_count,
   source ∈ {batch_sync, human_approval, human_override}, recorded_at
                          │
                          ▼  project_terms()
TermSnapshot(term, avg = Σ(pct×count)/Σcount, submissions_count = Σcount,
             risk_history carried forward)
```

Invariants, each covered by a test in `tests/core_memory/`:

| Invariant | Mechanism |
|---|---|
| Two assessments in one month both survive | Two facts, distinct `job_id`, one projected term |
| A human approval is not erased by a later batch | The approval is its own fact; the batch appends beside it |
| Redelivery does not double-count | `fact_id` is `{job_id}::{student_id}`; a re-put replaces in place |
| A redelivered batch cannot overwrite a human decision | `record_assessment` refuses to downgrade a human fact to `batch_sync` |
| `risk_history` and untouched terms survive | The projection carries prior history per term and keeps terms that have no facts |

The L3 read shape (`EpisodicStudentProfile.terms` → `TermSnapshot`) is unchanged,
so the risk detector and the review approval path see exactly what they saw
before — only the arithmetic behind the numbers changed.

**Migration note.** For a term that already has a legacy snapshot *and* gains its
first fact, the fact-derived value replaces the legacy number for that term
(facts are the only source of truth once they exist). Terms with no facts are
preserved verbatim. This is strictly better than the previous behaviour, which
replaced the snapshot on every batch regardless.

---

## 3. Deliberately not done

- **Audit sampling** of auto-synced records into the review queue (block B.3).
  Without it the label pool is conditioned on the system's own uncertainty and
  cannot estimate production accuracy. This is the next highest-value step.
- **Per-criterion label documents**, reviewer identity, `decision_ms`, reason
  codes and inter-rater weighting (blocks B.2 / B.5).
- **Retraction/supersession** of a label: an override is terminal, so a mistaken
  override cannot yet be corrected by a second one.
- **The term axis itself** (F-17): a term is still the calendar month of the
  upload. Only its integrity was fixed, not its definition. The `TermResolver`
  seam remains the place to fix the definition.
- **The teacher surface**: `api/teacher_views.py` has no override control and no
  rendering for the `overridden` status; overridden items simply leave the
  waiting queue.
