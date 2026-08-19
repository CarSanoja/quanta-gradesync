# Dev log — Implementation 001: auto-inferred manifest + confidence quarantine

**Date:** 2026-08-13
**Domain:** Implementation
**Executes:** Plan 001 (feedback 001)
**Verification:** `.venv/bin/pytest -q` → **82 passed / 0 failed** (was 53; +29
new tests). Clean `compileall`. No code comments. Every file ≤ 200 lines
(max 194).

## Improvement 1 — Auto-inferred manifest (done)

- `core/orchestration/catalog_defaults.py` (new): per-term registry
  `catalog-defaults.json` at the bucket root — subject bindings → grade_level
  + rubric + standard.
- `core/orchestration/manifest_inference.py` (new): grammar
  `{year}_{subject}_{class}_{assessment}`, validation against the event
  attributes (mismatch → `CatalogError`), submission listing (1 file = 1
  student, stem = student_id), `LocalManifestInferer` + `FallbackJobCatalog`.
- `core/orchestration/manifest_inference_gcs.py` (new): GCS variant
  (`list_blobs`).
- `catalog.py`: new `ManifestNotFound(CatalogError)` — only an *absent*
  manifest triggers inference; an *invalid* manifest fails loudly (never
  masked). `build_job_catalog` now returns the catalog with fallback.
- QR/OCR cover page: documented as a third mode over the same seam (not
  implemented in this cycle).

## Improvement 2 — Confidence quarantine (done)

- `schemas/review.py` (new): `ReviewItem` (idempotent id
  `{job_id}:{student_id}`, reasons, evidence with page+quote, document paths,
  proposed record) + `ReviewStatus` (PENDING/APPROVED/DISMISSED).
- `core/review/gate.py`: `ConfidenceGate` — quarantine if
  `min(confidence) < 0.85` or a criterion without cited evidence; exactly
  0.85 passes. Threshold: `GRADESYNC_CONFIDENCE_THRESHOLD`.
- `core/review/store.py`: `ReviewStore` protocol + `LocalReviewStore` (JSON
  per item) + `FirestoreReviewStore`.
- `core/review/service.py`: `ReviewService.approve` (writes to the SIS +
  updates L3 + marks APPROVED; a second approve → `ReviewStateError`),
  `dismiss`, `list_pending`.
- `core/orchestration/stages_sync.py` (new; extracted from
  `stages_outcome.py`, which stayed at 74 lines): the SYNC stage partitions by
  gate — low-confidence items go to the queue and **do not** touch the SIS or
  L3; `SISWriteResult.quarantined_count` (default 0, backward compatible).
- `api/review.py` (new): `GET /review/pending`,
  `POST /review/{id}/approve`, `POST /review/{id}/dismiss` with the same
  bearer token (401/403/404/409).
- `MemoryManager.persist_student_percentage`: incremental `TermSnapshot`
  merge on approval.

## Improvement 3 — ROI and pitch (done)

- README: optimized elevator pitch, input-flow matrix, six fundamental
  guarantees (incl. confidence escalation), ROI (12 h/week → ~10 min of
  exceptions; 14 days → <10 min), bucket-layout naming-convention section and
  the human review API table.
- `.env.example`: `GRADESYNC_CONFIDENCE_THRESHOLD=0.85`,
  `GRADESYNC_FIRESTORE_REVIEWS_COLLECTION=reviews`.

## New tests (29)

- `tests/orchestration/test_manifest_inference.py` (11): grammar valid/short/
  empty, end-to-end inference without `batch.json`, explicit manifest wins,
  invalid manifest not masked, subject mismatch, missing defaults, unbound
  subject, no gradable files, `ManifestNotFound`.
- `tests/review/test_confidence_gate.py` (7): exact 0.85 boundary passes /
  0.84 quarantines, missing evidence quarantines, weakest criterion decides,
  custom threshold, invalid values.
- `tests/review/test_review_flow.py` (3): full runner run with one student at
  0.6 → COMPLETED, SIS without that record, item with page+quote+reasons+
  path, L3 intact; approve → SIS + L3 + idempotency; dismiss closes without
  writing.
- `tests/api/test_review_endpoints.py` (8): auth 401/403, pending empty/
  populated, approve 200/404/409, dismiss without writing.

## Fixes during verification

1. `parse_lot_code`: whitespace-only prefixes are now treated as empty
   (previously they fell through to the convention error).
2. The `ReviewItem`'s `document_paths` uses the stable `gcs_uri` instead of
   the instance-ephemeral `local_path`.
3. Benchmark tests: the scripted evaluator now cites evidence at 0.95
   confidence (an agent that passes the gate), and the runner receives an
   explicit `review_store`.
4. Split by responsibility to stay ≤ 200 lines: `catalog_defaults.py`,
   `stages_sync.py`, `tests/review/flow_stack.py`,
   `tests/orchestration/inference_fixtures.py`.
