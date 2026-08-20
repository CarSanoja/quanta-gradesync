# Runbook — end-to-end run in GCP mode from a workstation

How to drive the full pipeline (fetch → grade → audit → risk → sync → verify →
optimize) against real Google Cloud services with the API running locally under
uvicorn. No Cloud Run deployment and no Pub/Sub subscription are required: the
push event is delivered with `curl`.

Measured results of the reference execution: `docs/reports/e2e-2026-08-19.md`.

## 1. Prerequisites

| Requirement | Value used in the reference run |
|---|---|
| GCP project | `quanta-gradesync` |
| ADC account | `contact@somosquanta.com` (`gcloud auth application-default login`) |
| Firestore | native database `(default)` |
| Bucket | `gs://quanta-gradesync-exams` |
| Gemini models | `gemini-3.5-flash` (grading), `gemini-3.5-flash-lite` (audit, rework) served from location `global` |
| Embeddings | `text-embedding-005` on `us-central1`, 768 dimensions |
| Python | 3.12+, dependencies installed in `.venv` |

IAM used by the workstation identity: `roles/datastore.user`,
`roles/aiplatform.user`, object read/write on the bucket, and
`datastore.indexes.create` for the one-time index below.

## 2. One-time: Firestore vector index

`FirestoreVectorMemory.query` uses `find_nearest`, which requires a vector index
on the collection that stores rubric embeddings. Without it every semantic
retrieval fails; the engine degrades to an empty context and logs a warning
instead of aborting, but the memory layer is then inert.

```bash
gcloud firestore indexes composite create \
  --project=quanta-gradesync \
  --collection-group=competencies \
  --query-scope=COLLECTION \
  --field-config=vector-config='{"dimension":"768","flat": "{}"}',field-path=embedding
```

Index creation takes a few minutes; queries fail until it reports `READY`:

```bash
gcloud firestore indexes composite list --project=quanta-gradesync \
  --format="table(name,state,fields)"
```

The dimension must match `GRADESYNC_EMBEDDING_MODEL` (768 for
`text-embedding-005`). Changing the embedding model requires a new index.

## 3. Upload the batch

The manifest inferer expects two things in the bucket:

- exam pages under a prefix whose last segment is the lot code
  `{year}_{subject}_{class_id}_{assessment}`;
- `catalog-defaults.json` **at the bucket root** (`GcsManifestInferer` downloads
  `gs://<bucket>/catalog-defaults.json`, not a per-prefix copy).

Generate the demo batch locally (deterministic) and upload it:

```bash
.venv/bin/python scripts/generate_sample_batch.py --target .local_data/sample_batch --seed 20260819

gcloud storage cp \
  .local_data/sample_batch/batches/2026_Matematicas_10A_Parcial1/*.jpg \
  gs://quanta-gradesync-exams/e2e/2026-08-19/batches/2026_Matematicas_10A_Parcial1/

gcloud storage cp \
  .local_data/sample_batch/catalog-defaults.json \
  gs://quanta-gradesync-exams/catalog-defaults.json
```

An explicit `batch.json` under the prefix is optional: `GcsJobCatalog` looks for
it first and falls back to inference when it is absent.

## 4. Build the push event

`.local_data/sample_batch/push-event.json` targets the local staging bucket, so
it cannot be reused as-is. Build one for the real bucket and prefix:

```bash
.venv/bin/python scripts/build_push_event.py \
  --bucket quanta-gradesync-exams \
  --prefix e2e/2026-08-19/batches/2026_Matematicas_10A_Parcial1 \
  --job-id e2e-2026-08-19-matematicas-10a-parcial1 \
  --trace-id 9c41e77b20f5a3d6 \
  --triggered-at 2026-08-19T18:30:00+00:00 \
  --output .local_data/sample_batch/push-event-gcp.json
```

The body is a Pub/Sub push envelope whose `message.data` is the base64 job event
(`job_id`, `bucket`, `exam_batch_prefix`, `class_id`, `subject`,
`triggered_at`, `trace_id`) — the contract `parse_push_body` validates. A raw
GCS `OBJECT_FINALIZE` notification carries the object metadata instead, so a
production subscription needs a translation step (Cloud Function, Workflow, or a
webhook branch) that derives these fields from the object path before the engine
sees them. The generated attributes (`bucketId`, `eventType`, `objectId`,
`lot_code`) mirror a notification but are not parsed.

`--job-id` is the idempotency key: reusing it returns `duplicate` and runs
nothing.

## 5. Environment

```bash
cat > .local_data/e2e.env <<'EOF'
GRADESYNC_LOCAL_MODE=false
GRADESYNC_GCP_PROJECT_ID=quanta-gradesync
GRADESYNC_GCP_REGION=us-central1
GRADESYNC_GEMINI_LOCATION=global
GRADESYNC_GCS_BUCKET=quanta-gradesync-exams
GRADESYNC_PUBSUB_TOPIC=projects/quanta-gradesync/topics/exam-batch-ingest
GRADESYNC_PUBSUB_PUSH_TOKEN=<random-token>
GRADESYNC_LOCAL_DATA_DIR=.local_data
GRADESYNC_BATCH_SETTLE_INTERVAL_SECONDS=5
GRADESYNC_BATCH_SETTLE_MAX_ROUNDS=6
EOF
```

Generate the token with `python -c "import secrets; print(secrets.token_urlsafe(24))"`.
It is only the shared secret between `curl` and the webhook; the Secret Manager
entry `gradesync-push-token` is for the deployed service.

Notes on the remaining settings:

- `GRADESYNC_SIS_BASE_URL` is intentionally unset. With an empty base URL in GCP
  mode `build_sis_connector` falls back to the local JSONL sink
  (`.local_data/sis_writes.jsonl`) and logs a warning at startup; readiness stays
  `ready`. Set the URL (plus `GRADESYNC_SIS_API_TOKEN`) as soon as a real SIS
  endpoint exists — the HTTP connector is used whenever the URL is non-empty.
- `GRADESYNC_MODEL_FALLBACK_LATENCY_SECONDS` defaults to 90 s. Grading a
  single-page exam with `gemini-3.5-flash` took 16–27 s in the reference run; a
  budget below that makes `FallbackEvaluator` discard the flash result and
  re-grade the exam with flash-lite (double cost, confidence scaled by 0.9).
- `GRADESYNC_CONFIDENCE_THRESHOLD` defaults to 0.85. Raise it (e.g. 0.99) only to
  exercise the quarantine path on purpose; see §9.

## 6. Run the API

```bash
set -a; . .local_data/e2e.env; set +a
.venv/bin/uvicorn autocurricula.api.main:app --host 127.0.0.1 --port 8080

curl -sS http://127.0.0.1:8080/healthz     # {"status":"ok"}
curl -sS http://127.0.0.1:8080/readyz      # {"status":"ready","mode":"gcp"}
```

`/readyz` returning `{"status":"ready","mode":"gcp"}` proves ADC, the project id and Firestore
connectivity; it does not exercise Vertex.

## 7. Fire the batch

```bash
set -a; . .local_data/e2e.env; set +a
curl -sS -X POST http://127.0.0.1:8080/webhooks/pubsub \
  -H "Authorization: Bearer $GRADESYNC_PUBSUB_PUSH_TOKEN" \
  -H "Content-Type: application/json" \
  --data @.local_data/sample_batch/push-event-gcp.json
# {"job_id":"...","status":"accepted"}

curl -sS -H "Authorization: Bearer $GRADESYNC_PUBSUB_PUSH_TOKEN" \
  http://127.0.0.1:8080/jobs/e2e-2026-08-19-matematicas-10a-parcial1
```

The webhook returns immediately and the job runs as a background task. Expect
the 8-exam demo batch to reach `completed` in roughly 45 s: fetch ≈ 3.7 s,
grade ≈ 28 s (8 concurrent multimodal calls), audit ≈ 3.2 s, risk ≈ 1.6 s,
sync ≈ 3.3 s, verify < 1 s, optimize ≈ 0 s.

`optimize` is a no-op unless `.local_data/calibration/` (grading) or
`.local_data/calibration_audits/` (auditor) contain samples: `CalibrationSet`
raises `FileNotFoundError` and `build_optimize_step` skips the optimizer.

## 8. Inspect the run

```bash
set -a; . .local_data/e2e.env; set +a
H="Authorization: Bearer $GRADESYNC_PUBSUB_PUSH_TOKEN"

curl -sS -H "$H" http://127.0.0.1:8080/jobs
curl -sS -H "$H" http://127.0.0.1:8080/jobs/<job-id>
curl -sS -H "$H" http://127.0.0.1:8080/review/pending
curl -sS -H "$H" http://127.0.0.1:8080/optimizer/report
open http://127.0.0.1:8080/console        # paste the same token in the console gate
```

Firestore holds the durable state: `checkpoints/<job-id>` (job record),
`checkpoints/<job-id>::session` (stage results), `profiles/<student-id>`,
`competencies/<class>::<criterion>` (mastery snapshots) plus the rubric
embedding document, `reviews/<job-id>:<student-id>`, and
`audit/<job-id>/events/<timestamp>` (spans, per-stage latency and token usage).

Per-stage tokens and cost come from the audit document:

```bash
.venv/bin/python - <<'PY'
from google.cloud import firestore
c = firestore.Client(project="quanta-gradesync")
job = "e2e-2026-08-19-matematicas-10a-parcial1"
for event in c.collection("audit").document(job).collection("events").stream():
    for span in event.to_dict()["spans"]:
        a = span["attributes"]
        if span["name"].startswith("Stage_"):
            print(span["name"], round(span["duration_ms"]), a.get("gen_ai.usage.input_tokens"),
                  a.get("gen_ai.usage.output_tokens"), a.get("gen_ai.calls"))
PY
```

The SIS sink is `.local_data/sis_writes.jsonl` while `sis_base_url` is empty.

## 9. Optional probes

**Idempotency.** POST the same body again after completion; the webhook answers
`{"status":"duplicate"}` and nothing runs — no SIS write, no new audit event,
`updated_at` unchanged.

**Quarantine / human review.** Restart the API with
`GRADESYNC_CONFIDENCE_THRESHOLD=0.99` and a fresh `--job-id`. Criteria below the
threshold are quarantined; crossing `GRADESYNC_BATCH_ANOMALY_THRESHOLD` (0.15)
trips the batch breaker, which moves the whole batch to review and writes
nothing to the SIS. `verify` then re-grades pending items with flash-lite for up
to `GRADESYNC_VERIFY_MAX_ITERATIONS` rounds. Approve one item with:

```bash
curl -sS -X POST -H "$H" http://127.0.0.1:8080/review/<review-id>/approve
```

This costs an extra flash batch plus the rework calls (~$0.36 for the demo
batch); run it only when the review path is what you need to demonstrate.

## 10. Cleanup

Leave the uploaded objects in place if later runs need them. Otherwise:

```bash
gcloud storage rm -r gs://quanta-gradesync-exams/e2e/2026-08-19/
gcloud storage rm gs://quanta-gradesync-exams/catalog-defaults.json
```

Firestore documents from a run (delete only what you no longer need):

```bash
.venv/bin/python - <<'PY'
from google.cloud import firestore
c = firestore.Client(project="quanta-gradesync")
job = "e2e-2026-08-19-matematicas-10a-parcial1"
for name in ("checkpoints",):
    for suffix in ("", "::session"):
        c.collection(name).document(job + suffix).delete()
for doc in c.collection("audit").document(job).collection("events").stream():
    doc.reference.delete()
PY
```

The vector index is reusable; keep it. Stop uvicorn with `Ctrl+C` (or
`pkill -f "uvicorn autocurricula.api.main:app"`).
