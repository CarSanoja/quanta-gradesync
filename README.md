# AutoCurricula & GradeSync Engine

A production-grade, asynchronous microservice for K-12 backoffice automation and the
"All Things Agentic" competition. The engine breaks the standard chat loop: it runs
100% in the background, triggered by Cloud Storage uploads and Pub/Sub messages, and
replaces manual student exam grading, curricular standard reconciliation, and early
dropout detection.

Built on Google Cloud Run + Pub/Sub + Firestore, using the Google Agent Development
Kit (ADK) with Gemini 3.5 Pro (deep multimodal reasoning) and Gemini 3.5 Flash
(high-speed structured extraction). Every LLM call and every inter-component message
uses strict Pydantic v2 structured-output schemas — zero loose strings.

## Elevator pitch

In goes a batch of scanned exams; out come audited grades in the SIS, curriculum
coverage maps, and early dropout alerts. Teachers don't "use" an app or learn an
interface: they drop files in a bucket and get their evenings back. Pure backoffice
infrastructure.

**Teacher time saved:** from ~12 weekly hours of manual grading to zero
transcription and ~10 minutes of exception review. **Time-to-feedback:** from a
14-day grading cycle to under 10 minutes after the scan lands in the bucket.

### Input flows

| Input | Source | Frequency |
|-------|--------|-----------|
| Scanned exam batch (handwritten PDFs/images) | Teacher or front office | Per assessment |
| Batch metadata (subject, grade, active rubric) | **Auto-inferred from the path/lot-code convention** or explicit `batch.json` | Automatic per event |
| Rubrics + national curriculum standard | Pedagogical coordination | Once per term |
| Calibration samples (human ground truth) | Validated historical assessments | Periodic (feeds self-improvement) |
| SIS/LMS credentials & connectors | IT / administration | One-time setup |

### Fundamental guarantees

1. **Transactional idempotency** — even if Pub/Sub delivers the message multiple
   times, an exam is never duplicated or computed twice in the SIS.
2. **Absolute defensibility** — every grade carries an `EvidenceSpan` with a verbatim
   quote and page number; parent complaints are answered with evidence from the
   student's own manuscript.
3. **Confidence-threshold escalation** — ambiguous answers or illegible handwriting
   are never guessed: they go to quarantine (`REQUIRES_HUMAN_REVIEW`) with the exact
   page and cited excerpt pre-highlighted, for one-click teacher approval.
4. **Deterministic, explainable risk** — early-warning alerts come from math
   (z-scores, longitudinal slopes over L3 history), not free-form LLM opinion.
5. **Anti-gaming self-improvement** — the prompt optimizer only promotes variants
   that improve human agreement (QWK/MAE), actively blocking variance collapse or
   artificial average-to-middle scores.
6. **Long-running fault tolerance** — persistent per-stage checkpoints; if
   infrastructure is interrupted, the pipeline resumes exactly at the pending stage
   without recomputing prior work.

## What it does

1. **Ingest** — A school uploads a batch of scanned handwritten exams / PDFs to a GCS
   bucket. GCS notifies Pub/Sub; Pub/Sub pushes the event to the Cloud Run service.
2. **Grade** — The grading agent (Gemini 3.5 Pro) performs multimodal OCR and rubric
   semantic assessment, producing criterion-level scores with cited evidence spans.
3. **Audit** — The curriculum auditor (Gemini 3.5 Flash) cross-references results
   against ministry curriculum competencies.
4. **Detect risk** — The risk detector scores anomalies and retention early-warning
   signals from episodic student history.
5. **Sync with confidence gate** — Records whose extraction confidence is at or above
   `GRADESYNC_CONFIDENCE_THRESHOLD` (default 0.85) with cited evidence are written
   into the SIS. Anything below the threshold, or scored without evidence, is
   quarantined as `REQUIRES_HUMAN_REVIEW` — never guessed, never silently synced —
   with the page, the cited excerpt, and the proposed record ready for one-click
   approval.
6. **Verify (agentic closure)** — A goal verifier checks the job's mission
   (every submission graded, audited and risk-assessed; SIS write clean; every
   quarantine accounted for) and runs a **bounded rework loop**: quarantined
   submissions are re-graded by a second-opinion evaluator; those that clear the
   gate get their review item updated with the new record and rework notes — still
   pending one-click human approval. The loop stops on convergence, no-progress,
   or the iteration budget (`GRADESYNC_VERIFY_MAX_ITERATIONS`), and reports
   `pending_human_approval` vs `unresolved` explicitly.
7. **Evolve** — Meta-optimizers (one per evolving prompt: grading and curriculum
   auditor) run **convergence loops of tournaments**: each cycle proposes
   `GRADESYNC_OPTIMIZER_CANDIDATES` mutations, re-evaluates every candidate against
   the same human ground-truth calibration set, gates them with the anti-gaming
   validator (variance collapse, constant outputs, ground-truth contact), promotes
   only the best accepted mutation — and keeps cycling until the marginal
   improvement falls below
   `GRADESYNC_OPTIMIZER_CONVERGENCE_MIN_IMPROVEMENT` or the cycle budget
   (`GRADESYNC_OPTIMIZER_MAX_CYCLES`) is exhausted.

## Architecture

```text
  +---------------+  upload batch   +--------------+  notification  +---------------------+
  | School Staff  |--------------->| | GCS Bucket  |-------------->| | Pub/Sub Topic      |
  +---------------+  (scans/PDFs)  +--------------+  (object       | | exam-batch-ingest  |
                                    (notify config)   finalize)    +----------+----------+
                                                                       push (OIDC + token)
                                                                         |
                                                                         v
                         +-----------------------------------------------+-----------------+
                         | Cloud Run Service  (min-instances=1, timeout=900, no cold starts) |
                         | FastAPI + uvicorn + uvloop + httptools, Pydantic v2 everywhere    |
                         |                                                               |
                         |   api/main.py       health + readiness endpoints               |
                         |   api/webhooks.py   Pub/Sub push handler -> PubSubJobEvent     |
                         +-------------------------------+-------------------------------+
                                                         |
                            ADK orchestration graph  (core/orchestration)
                                                         |
         +--------------------+--------------------+-----+---------------+-----------------+
         |                    |                    |                     |                 |
         v                    v                    v                     v                 v
  +---------------+  +-----------------+  +-----------------+  +----------------+  +---------------+
  | GCS Fetcher   |  | Grading Agent   |  | Curriculum      |  | Risk Detector  |  | SIS Connector |
  | (tools/)      |  | Gemini 3.5 Pro  |  | Auditor         |  | Gemini 3.5     |  | (tools/, httpx)|
  | stage objects |  | multimodal OCR  |  | Gemini 3.5      |  | Flash anomaly  |  | grade writes  |
  | to local disk |  | + rubric        |  | Flash ministry  |  | + retention    |  | to SIS API    |
  +---------------+  | semantics       |  | cross-reference |  | early warning |  +---------------+
                     +-----------------+  +-----------------+  +----------------+
         |                    |                    |                     |                 |
         +--------------------+---------- L1/L2/L3 memory hierarchy ------+-----------------+
                                                         |
                                    state checkpoints -> Firestore (every step, resumable)
                                                         |
                                                         v
                                          +----------------------------+
                                          | Meta-Optimizer Agent       |
                                          | calibration vs human       |
                                          | ground truth, prompt       |
                                          | mutation, anti-gaming      |
                                          | validator                  |
                                          +----------------------------+
```

## Memory hierarchy

| Tier | Name | Backend | Contents | Lifetime |
|------|------|---------|----------|----------|
| L1 | Working memory / session state | In-process ephemeral store | Execution-graph context per Pub/Sub job: staged file refs, intermediate graded artifacts, checkpoints | Duration of one job |
| L2 | Vector search / short-term | Firestore vector search + Vertex text-embeddings (`GRADESYNC_EMBEDDING_MODEL`); local mode uses a real TF-IDF index | Dynamic rubrics, curriculum guideline chunks, batch-level calibration samples | Cross-job semantic retrieval |
| L3 | Managed cloud memory | Firestore | Episodic student profiles, cross-term class competency snapshots, evolved prompt registry | Persistent |

Every GCP client (Pub/Sub, Firestore, GCS, SIS) sits behind a Protocol with a real
local implementation selected when `GRADESYNC_LOCAL_MODE=true`, so the entire test
suite runs offline with no GCP credentials (in-memory stores, local-dir staging,
jsonl append).

## Local-mode quickstart

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
cp .env.example .env
pytest
```

Run the API locally:

```bash
uvicorn autocurricula.api.main:app --host 0.0.0.0 --port 8080 --loop uvloop --http httptools
```

Test markers:

- `pytest -m benchmark` — throughput/concurrency stress tests
- `pytest -m calibration` — ground-truth prompt quality tests

## Environment variables

All variables use the `GRADESYNC_` prefix and are read from the environment or a
`.env` file (see `.env.example`). `LOCAL_MODE` defaults to `true` when
`GCP_PROJECT_ID` is unset.

| Variable | Default | Description |
|----------|---------|-------------|
| `GRADESYNC_GCP_PROJECT_ID` | *(empty)* | GCP project id; unset implies local mode |
| `GRADESYNC_GCP_REGION` | `us-central1` | GCP region for Cloud Run / Vertex AI |
| `GRADESYNC_GEMINI_PRO_MODEL` | `gemini-3.5-pro` | Deep multimodal reasoning model |
| `GRADESYNC_GEMINI_FLASH_MODEL` | `gemini-3.5-flash` | High-speed structured extraction model |
| `GRADESYNC_EMBEDDING_MODEL` | `text-embedding-005` | Vertex embedding model for L2 semantic retrieval (GCP mode) |
| `GRADESYNC_PUBSUB_TOPIC` | *(empty)* | Ingest topic, e.g. `projects/<pid>/topics/exam-batch-ingest` |
| `GRADESYNC_PUBSUB_PUSH_TOKEN` | *(empty)* | Shared token verified on every push delivery |
| `GRADESYNC_GCS_BUCKET` | *(empty)* | Bucket receiving exam batch uploads |
| `GRADESYNC_GCS_LOCAL_STAGING_DIR` | `.staging` | Local directory used to stage downloaded objects |
| `GRADESYNC_FIRESTORE_JOBS_COLLECTION` | `jobs` | Job registry collection |
| `GRADESYNC_FIRESTORE_CHECKPOINTS_COLLECTION` | `checkpoints` | Workflow checkpoint collection |
| `GRADESYNC_FIRESTORE_PROFILES_COLLECTION` | `profiles` | L3 episodic student profiles |
| `GRADESYNC_FIRESTORE_COMPETENCIES_COLLECTION` | `competencies` | L3 class competency snapshots |
| `GRADESYNC_FIRESTORE_PROMPTS_COLLECTION` | `prompts` | Evolved prompt registry |
| `GRADESYNC_FIRESTORE_REVIEWS_COLLECTION` | `reviews` | Confidence-quarantined review queue |
| `GRADESYNC_CONFIDENCE_THRESHOLD` | `0.85` | Minimum grading confidence (0-1) to auto-sync; below goes to human review |
| `GRADESYNC_OPTIMIZER_CANDIDATES` | `3` | Tournament size: candidate prompt mutations evaluated per optimizer cycle |
| `GRADESYNC_OPTIMIZER_MAX_CYCLES` | `3` | Convergence budget: optimizer cycles per trigger |
| `GRADESYNC_OPTIMIZER_CONVERGENCE_MIN_IMPROVEMENT` | `0.01` | Marginal MAE improvement below which the optimizer stops cycling |
| `GRADESYNC_VERIFY_MAX_ITERATIONS` | `2` | Bounded rework iterations in the verify stage |
| `GRADESYNC_HARNESS_MAX_CALLS_PER_ITEM` | `4` | Max agent invocations per exam before isolating it (blast-radius containment) |
| `GRADESYNC_SCHEMA_REPAIR_ATTEMPTS` | `2` | Bounded JSON-contract self-repair attempts before quarantine |
| `GRADESYNC_BATCH_ANOMALY_THRESHOLD` | `0.15` | Quarantine ratio above which the whole batch's auto-sync is suspended |
| `GRADESYNC_VARIANCE_COLLAPSE_RATIO` | `0.20` | Allowed score-variance drop vs ground truth before the anti-gaming sensor rejects |
| `GRADESYNC_OBJECTIVE_GATE_ENABLED` | `true` | Require the composite objective gate (QWK/MAE/bias) to promote prompts |
| `GRADESYNC_OBJECTIVE_QWK_MIN` | `0.85` | Minimum quadratic weighted kappa for promotion (grading scope) |
| `GRADESYNC_OBJECTIVE_MAE_MAX` | `0.4` | Maximum MAE for promotion |
| `GRADESYNC_OBJECTIVE_BIAS_ABS_MAX` | `0.1` | Maximum absolute bias for promotion (grading scope) |
| `GRADESYNC_SIS_BASE_URL` | *(empty)* | School Information System API base URL |
| `GRADESYNC_SIS_API_TOKEN` | *(empty)* | SIS bearer token |
| `GRADESYNC_LOCAL_MODE` | auto | `true` selects local offline implementations |
| `GRADESYNC_LOCAL_DATA_DIR` | `.local_data` | Root for local-mode persisted data |
| `GRADESYNC_API_HOST` | `0.0.0.0` | Bind host |
| `GRADESYNC_API_PORT` | `8080` | Bind port |

## Deploy with Cloud Build

```bash
gcloud builds submit . \
  --config cloudbuild.yaml \
  --substitutions=_REGION=us-central1,_REPOSITORY=autocurricula,_SERVICE_NAME=autocurricula-gradesync,_GCS_BUCKET=my-bucket,_PUBSUB_PUSH_TOKEN=$(openssl rand -hex 24),_SIS_API_TOKEN=***,_SIS_BASE_URL=https://sis.example.edu/api/v1
```

Cloud Build builds the container, pushes it to Artifact Registry (`$_REPOSITORY`), and
deploys to Cloud Run with `--min-instances=1` (zero cold starts), `--timeout=900`, the
runtime service account from `$_SERVICE_ACCOUNT`, and env vars injected with the
`^^^,^^^` multi-value separator.

One-time setup:

```bash
gcloud artifacts repositories create autocurricula --repository-format=docker --location=us-central1
gcloud iam service-accounts create autocurricula-runner
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member=serviceAccount:autocurricula-runner@PROJECT_ID.iam.gserviceaccount.com \
  --role=roles/pubsub.subscriber
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member=serviceAccount:autocurricula-runner@PROJECT_ID.iam.gserviceaccount.com \
  --role=roles/datastore.user
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member=serviceAccount:autocurricula-runner@PROJECT_ID.iam.gserviceaccount.com \
  --role=roles/storage.objectAdmin
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member=serviceAccount:autocurricula-runner@PROJECT_ID.iam.gserviceaccount.com \
  --role=roles/aiplatform.user
```

## Pub/Sub push setup

```bash
gcloud pubsub topics create exam-batch-ingest

gcloud storage buckets notifications create gs://BUCKET \
  --topic=exam-batch-ingest --event-types=object_finalize

gcloud pubsub subscriptions create exam-batch-ingest-push \
  --topic=exam-batch-ingest \
  --push-endpoint=SERVICE_URL/webhooks/pubsub \
  --push-auth-service-account=autocurricula-runner@PROJECT_ID.iam.gserviceaccount.com \
  --ack-deadline=600 \
  --message-retention-duration=1h
```

Notes:

- The push endpoint is the deployed Cloud Run URL plus `/webhooks/pubsub`
  (handled by `autocurricula.api.webhooks`).
- Every delivery must carry the shared `GRADESYNC_PUBSUB_PUSH_TOKEN` (query param or
  `Authorization` header) — the handler rejects deliveries without it before any
  work is acked.
- Grant the push-auth service account `roles/run.invoker` on the Cloud Run service.
- The handler returns `200` (accepted/duplicate) so Pub/Sub acks; non-2xx (or
  timeout) lets Pub/Sub retry, and the orchestrator resumes from the last Firestore
  checkpoint.

## Agent Harness (governance, containment, control)

The engine ships a domain-agnostic harness (`src/autocurricula/core/harness/`) that
separates governance from the model, in three layers:

- **Execution harness (runtime)** — every external action passes a deterministic
  permission pipeline `DENY > QUARANTINE > ALLOW` (writes to students outside the
  batch manifest are blocked in memory, before any network call); per-exam budgets
  (`GRADESYNC_HARNESS_MAX_CALLS_PER_ITEM`, schema-repair attempts) contain runaway
  reasoning; a failing exam is isolated (blast radius) instead of failing the job;
  and a faithfulness verifier checks every cited `EvidenceSpan` quote against the
  page transcript when one exists — a hallucinated quote zeroes the confidence and
  lands in quarantine.
- **Evaluation harness (offline)** — prompt promotion requires the composite
  objective gate (`QWK ≥ 0.85 ∧ MAE ≤ 0.4 ∧ |Bias| < 0.1`, scope-adjusted) on top of
  the anti-gaming validator; the CI suite runs an anti-regression gate against the
  committed golden baseline (`tests/harness/golden_baseline.json`).
- **Circuit breakers & governance** — if more than 15% of a batch falls into
  `REQUIRES_HUMAN_REVIEW`, automatic sync for the entire batch is suspended
  (defective scan, wrong rubric, or model drift are the working hypotheses); and
  every SIS record carries a provenance ledger (`prompt_version_sha` + per-evidence
  SHA-256 hashes) so any audit can trace exactly which prompt version and which
  cited fragment produced each grade.

The harness operates on generic concepts (`ToolAction`, risk levels, budgets,
thresholds) — recycling it into another agent means re-registering rules and
thresholds, with no domain code inside.

## Product documentation

Two living documents, updated with every implementation cycle, live in
[`docs/product/`](docs/product/README.md):

- [How the GradeSync Engine Works — A Cold Run](docs/product/how-it-works.md)
- [The GradeSync Engine as a Product](docs/product/product-overview.md)

The append-only development log (architecture notes, audits, feedback, plans, and
implementation records) lives in [`docs/bitacora/`](docs/bitacora/README.md).

## Batch naming convention (zero-form intake)

Nobody fills a manifest per assessment. Two supported intake modes, tried in order:

1. **Explicit manifest** — `batch.json` inside the batch prefix (full control, e.g.
   pre-packaged submissions with rubric and standard).
2. **Auto-inference** — when no `batch.json` exists, the engine infers the batch from
   the bucket layout:

```text
<bucket>/
├── catalog-defaults.json          one-time per term, by pedagogical coordination:
│                                  { "bindings": [ { subject, grade_level, rubric,
│                                    curriculum_standard } ] }
└── batches/
    └── 2026_Matematicas_10A_Parcial1/     {year}_{subject}_{class}_{assessment}
        ├── ana-torres.jpg                  one file per student; the file stem is
        ├── luis-gomez.pdf                  the student id / submission id
        └── ...
```

Rules that keep inference honest: the lot-code subject and class must match the
Pub/Sub event attributes (mismatch fails the job loudly), the subject must have a
binding in `catalog-defaults.json`, and at least one gradable file
(jpg/jpeg/png/pdf/heic) must exist under the prefix. An invalid `batch.json` is
never silently replaced by inference — it fails with the validation error. A
pre-printed cover page with a QR/OCR lot code is a planned third mode over the
same seam.

## Human review API (the one-click approval)

All endpoints require the same `Authorization: Bearer $GRADESYNC_PUBSUB_PUSH_TOKEN`.

| Method & path | Purpose |
|---------------|---------|
| `GET /review/pending` | Quarantined items with page, cited excerpt, reasons, and proposed record |
| `POST /review/{review_id}/approve` | Writes the proposed record to the SIS, updates L3 history, marks approved (`409` if already decided) |
| `POST /review/{review_id}/dismiss` | Closes the item without writing to the SIS |

## Project layout

```text
src/autocurricula/
├── config/            Settings + lazy GCP client factories
├── schemas/           Pydantic v2 structured-output models
├── tools/             SIS connector, GCS fetcher, vector search
├── agents/            Grading, curriculum audit, risk, meta-optimizer agents
├── core/memory/       L1 session, L2 vector, L3 managed memory
├── core/evolution/    Prompt mutation, anti-gaming validators
├── core/review/       Confidence gate, review queue, approval service
├── core/orchestration/  Google ADK workflow execution graph
└── api/               FastAPI app + Pub/Sub push webhook + review API
```
