# Dev log — Plan 001: auto-inferred manifest + confidence quarantine

**Date:** 2026-08-13
**Domain:** Planning
**Solves:** Feedback 001 (points 1 and 2; point 3 is documentation)
**Status:** Executed — see implementation entry 001

## Improvement 1 — Convention-based auto-inferred manifest

**Problem:** `LocalJobCatalog`/`GcsJobCatalog` require a per-batch
`batch.json` (`catalog.py`). Filling it per assessment breaks the "upload
files and disappear" promise.

**Design:**
- New `ManifestNotFound(CatalogError)` exception to distinguish "no manifest"
  from "the manifest exists but is invalid" (the latter is **never** silently
  replaced: it fails loudly).
- `FallbackJobCatalog`: tries the explicit manifest; if absent, infers.
- **Convention grammar** for the last prefix segment:
  `{year}_{subject}_{class}_{assessment}` (e.g.
  `2026_Matematicas_10A_Parcial1`). Subject and class must match the Pub/Sub
  event (source of truth); any mismatch or ambiguous token → `CatalogError`
  with the exact reason. The system never guesses.
- **Submission listing:** every allowed-mime file under the prefix is one
  submission; `student_id`/`submission_id` = file stem (the teacher scans
  `juanp001.jpg`). Local: staging walk; GCP: `list_blobs`.
- **Rubric registry** `catalog-defaults.json` at the bucket root (once per
  term, set by coordination): maps subject → `grade_level` + `Rubric` +
  `CurriculumStandard`. Missing binding → `CatalogError`.
- QR/OCR cover page: documented as a future third mode over the same seam.

## Improvement 2 — Confidence quarantine (0.85 gate)

**Problem:** writing 100% of grades to the SIS without human validation is
unacceptable for formal K-12.

**Design (new `core/review/` domain):**
- `schemas/review.py`: `ReviewItem` (deterministic id
  `{job_id}:{student_id}` → idempotent re-enqueue; reasons; evidence with
  page+quote as the "pre-highlighted excerpt"; document paths; proposed
  record; timestamps) + `ReviewStatus` (PENDING/APPROVED/DISMISSED).
- `core/review/gate.py`: `ConfidenceGate` — quarantine if
  `min(criterion confidences) < threshold` or any criterion lacks cited
  evidence; exactly 0.85 passes. Threshold via
  `GRADESYNC_CONFIDENCE_THRESHOLD`.
- `core/review/store.py`: `ReviewStore` protocol + `LocalReviewStore` (JSON
  per item) + `FirestoreReviewStore`.
- `core/review/service.py`: `ReviewService.approve` (writes to the SIS +
  updates L3 + marks APPROVED; second approve → state error), `dismiss`,
  `list_pending`.
- **SYNC stage rewritten:** partitions records per student; low-confidence
  ones go to the review queue and **never** touch the SIS or pollute L3
  (episodic profiles only record confirmed outcomes);
  `SISWriteResult.quarantined_count` (default 0, backward compatible).
- **API:** `GET /review/pending`, `POST /review/{id}/approve`,
  `POST /review/{id}/dismiss` with the same bearer token — the one-click
  approval.
- RISK still evaluates all submissions (early warning does not wait for
  approval).

## Improvement 3 — ROI and pitch (documentation)

- README: optimized elevator pitch, input-flow matrix, six fundamental
  guarantees (incl. confidence escalation), ROI (12 h/week → ~10 min of
  exceptions; 14 days → <10 min).
- `.env.example`: `GRADESYNC_CONFIDENCE_THRESHOLD=0.85`,
  `GRADESYNC_FIRESTORE_REVIEWS_COLLECTION=reviews`.

## Test plan

1. `tests/orchestration/test_manifest_inference.py` — grammar (happy, short
   code, empty), end-to-end inference without `batch.json`, explicit manifest
   wins, invalid manifest is not masked, subject mismatch, missing defaults,
   unbound subject, no gradable files.
2. `tests/review/test_confidence_gate.py` — 0.85 boundary passes / 0.84
   quarantines; missing evidence quarantines; weakest criterion decides.
3. `tests/review/test_review_flow.py` — full runner run with one student at
   0.6: COMPLETED, SIS without that record, item with page+evidence+reasons,
   L3 intact; approve → SIS + L3 + double-approve fails; dismiss closes
   without writing.
4. `tests/api/test_review_endpoints.py` — auth 401/403, empty/populated
   pending, approve 200/404/409.
5. Full suite green; benchmarks adjusted (the scripted evaluator now cites
   evidence, like a gate-passing agent).

## Impact on existing code

- `JobRunner`/`build_pipeline`/`build_sync_step` gain `review_store` and
  `confidence_threshold` (explicit constructors: `bench_fixtures.py` and
  `dependencies.py` updated).
- `MemoryManager` gains a public `persist_student_percentage` (unit approval).
- No behavior changes in RISK/AUDIT/OPTIMIZE or in idempotency.
