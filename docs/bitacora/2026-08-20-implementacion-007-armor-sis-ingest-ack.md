# Dev log — Implementation 007: Model Armor, visible SIS, ingest panel, live trace, ack-on-success

**Date:** 2026-08-20
**Domain:** Implementation
**Fulfills:** SOL-014 (hackathon execution sprint, phase 2 — three parallel work streams)
**Verification:** offline suite **258 passed / 6 skipped** (was 208/4; +50 tests); live armor suite 2/2 against Vertex flash-lite.

## Model Armor and legibility-aware confidence (Fleet: Model Armor component)

- `core/armor/`: per-submission injection screen at the GradeGuard seam. Cloud
  mode uses a `gemini-3.5-flash-lite` structured call over the page images
  (verdict: detected/quote/severity/rationale); local mode uses a deterministic
  scripted detector so the full path is covered offline. Verdicts persist in
  session state and force quarantine at sync with
  `prompt injection suspected: <quote>` as the first review reason — the
  proposed grade is preserved for the reviewer, never auto-synced. The screen
  fails open with a logged verdict; `armor_enabled` is the kill switch.
- Legibility metric (`core/armor/legibility.py`): grayscale Laplacian variance
  x contrast stddev → score in [0,1]. Measured on the real demo batch: solid
  scans 662–862 blur-variance / 20–25 contrast; camila-rios 45.6 / 6.4 →
  score 0.191 (5x separation on both axes). Effective confidence =
  model confidence x factor (linear below full-trust 0.70, floor 0.50), feeding
  both the confidence gate and the SIS permission payload — the camila-rios
  class of degraded scans now quarantines even at self-reported 0.98.
- Live proof: `tests/live/test_armor.py` — julian-pardo detected, ana-torres
  clean, against the real model.

## Visible SIS (the missing demo surface)

- `tools/sis_firestore.py`: cloud-mode fallback for an empty `sis_base_url` is
  now a Firestore `sis_records` ledger (was an ephemeral `/tmp` JSONL invisible
  to any viewer). Deterministic doc ids (job+student) make redelivery
  idempotent by construction; documents carry per-criterion scores, competency
  codes, provenance and term, with enrichment failures degrading to empty
  fields rather than failing the grade write.
- `GET /sis/records` + a console "SIS ledger" panel polling it — grades
  visibly appear in the school system as the pipeline syncs.

## Ingest panel (upload without leaving the console)

- `POST /ingest/exam`: multipart upload validated against the same lot-code and
  extension rules as the notification path; `ifGenerationMatch=0` turns a GCS
  412 into a domain-aware collision dialog — Replace scan (new version; bucket
  versioning now enabled preserves the processed original) or Different student
  (explicit rename; the file stem IS the student id, never auto-renamed).
- `POST /ingest/sample-batch`: server-side GCS copy of the 8 demo objects to a
  fresh prefix; the resulting OBJECT_FINALIZE notifications start the deployed
  pipeline with no manual HTTP call. Runtime SA upgraded to `objectAdmin` on
  the bucket.

## Live trace (Fleet: Observability component)

- `GET /jobs/{job_id}/trace` reads the persisted span tree, metrics snapshot
  and audit tail (local JSONL / Firestore subcollection). Console "Live trace"
  panel animates per-stage pills while a job runs and renders span durations,
  `gen_ai.usage.*` tokens and error marks once persisted.

## Ack-on-success (fixes deployment finding #6)

- The webhook now awaits the pipeline inside the push request: success → 200
  with the terminal stage; mid-pipeline failure → 5xx, the delivery is NOT
  acknowledged, Pub/Sub redelivers and the job resumes from its checkpoint
  (`tests/api/test_webhook_retry.py` proves fail → redeliver → resume without
  recomputing finished stages). A failed job record no longer short-circuits
  as duplicate. `--no-cpu-throttling` dropped from the deploy config.

## Process

Three parallel workflow agents on disjoint file sets (console/SIS/ingest/trace,
armor/trust, webhook semantics), orchestrator-reviewed and committed as nine
atomic commits. Live verification ran after credential re-auth: armor 2/2;
bucket versioning + IAM applied. Pending: redeploy with the new image and a
production run validating armor quarantine and SIS ledger end to end.
