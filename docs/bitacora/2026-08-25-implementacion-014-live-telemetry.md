# Dev log — Implementation 014: native traces, live mission control, committed dashboard

**Date:** 2026-08-25
**Domain:** Implementation
**Fulfills:** observability that a judge or an operator can open, not a claim in a README
**Verification:** offline suite **599 passed / 8 skipped** on the integrator's closing run (was 506/8 before this cycle). Everything that requires the deployed revision — the Cloud Trace explorer check, the Firestore live subcollection, the Monitoring dashboard import — is **pending the next production deploy**. No latency, cost or volume figure is claimed in this entry.

Until this cycle the engine had honest telemetry that nobody outside the
process could see: typed spans held in a `Recorder`, flushed to the audit trail
at job end. Good enough for a post-mortem, useless while a batch is running and
invisible to Google Cloud's own tooling. Three layers close that, over the same
run and the same span tree.

## Layer 1 — the trace is deterministic, so the job id is the address

`core/telemetry/trace_ids.py` derives the Cloud Trace id from the job's own
`trace_id`: identity when it is already 32 hex characters, the first 32 hex of
its SHA-256 otherwise. That single decision removes the lookup table nobody
maintains — with a job id in hand, the trace URL is computable offline, and the
console can render an Open-in-Cloud-Trace link per job without a round trip.

Under that root the tree is the one the pipeline already had —
`Stage_<name>` → `Grading_<submission_id>` with `ArmorScreen` and
`FaithfulnessVerification` children, `CapabilityDenied` where the permission
gate refused — plus what we were throwing away: ADK emits a `call_llm` span for
every Gemini call, carrying `gcp.vertex.agent.llm_request` /
`gcp.vertex.agent.llm_response`, `gen_ai.request.model`, the token usage
attributes and the finish reason. Exporting through
`google.adk.telemetry.google_cloud.get_gcp_exporters` nests those under our
spans instead of stranding them in a parallel, parentless trace. Structured JSON
logs on stdout carry `logging.googleapis.com/trace`, so Cloud Logging and Cloud
Trace show the same run from either side. New dependency:
`opentelemetry-exporter-otlp-proto-http` (the ADK exporters import it lazily and
degrade to a warning without it — a silent half-observability we would rather
not ship).

## Layer 2 — mission control: the run visible while it runs

The `Recorder` now also streams typed `LiveEvent`s: span start, span end, LLM
exchange with prompt and response excerpts, armor verdict, permission denial.
Storage follows the audit trail it belongs to —
`audit/{job_id}/live/{seq:06d}` in Firestore, `seq` monotonic per job from 1 so
lexical order is chronological order; `{local_data_dir}/live/{job_id}.jsonl`
locally. `GET /jobs/{job_id}/live` serves them and the new mission-control view
of `/console` renders them: fleet board, event ticker, payload drawer,
per-student reasoning chains, the Cloud Trace link and a JSONL export of exactly
what the API returned.

The schema is a `FrozenStrictModel` (`schemas/live_events.py`) written before
any of the three streams started, precisely so the tracer, the API and the
console could be built in parallel against one contract rather than three
guesses about each other.

## Layer 3 — metrics and a dashboard that lives in the repo

`enable_cloud_metrics` pushes OTel metrics on the periodic reader, and
`docs/gcp/monitoring-dashboard.json` is a real Cloud Monitoring dashboard —
mosaic layout over `run.googleapis.com` request count by response class, p95
latency, instance count by state, CPU and memory utilization, plus a logs panel
filtered to the service. It is committed and imported with one `gcloud`
command (`docs/gcp/README.md`), not clicked together in the console and
screenshotted. Deliberate restraint: the dashboard uses only Cloud Run platform
metrics, which the platform emits whether or not our export is on, so the panels
cannot go blank because of an application-side flag.

## The switch a DPO can be shown

`GRADESYNC_TELEMETRY_CAPTURE_CONTENT=false` removes every prompt and response
excerpt from spans, live events and logs while keeping names, timings, token
counts, model ids, armor verdicts and permission decisions. The distinction
matters for a school: the fleet board stays fully readable — structure is
metadata, not content — and only the payload drawer goes quiet.
`GRADESYNC_TELEMETRY_PAYLOAD_MAX_CHARS` is the middle setting for anyone who
wants to debug a bad grade without carrying a full manuscript transcript into
telemetry storage. Two independent reasons no page image can leak into a span:
ADK's request attribute excludes inline bytes, and our excerpts are text-only
and capped.

Six new settings, all `GRADESYNC_`-prefixed: `TELEMETRY_LIVE_ENABLED`,
`TELEMETRY_CLOUD_TRACE_ENABLED`, `TELEMETRY_CLOUD_METRICS_ENABLED`,
`TELEMETRY_CAPTURE_CONTENT`, `TELEMETRY_PAYLOAD_MAX_CHARS`, `LOG_JSON`. The
first four are set on every deploy by `cloudbuild.yaml`; cloud trace and metric
export are no-ops in local mode, so the offline suite and any laptop run stay
exactly as offline as before.

## Deploy and operations surface

- `cloudbuild.yaml` — the four telemetry flags on the Cloud Run revision.
- `docs/runbooks/observability.md` — IAM for
  `autocurricula-runner@quanta-gradesync.iam.gserviceaccount.com`
  (`roles/telemetry.tracesWriter`, `roles/monitoring.metricWriter`,
  `roles/logging.logWriter`), enabling `telemetry.googleapis.com`, verifying a
  trace by its 32-hex id, reading live events from Firestore or the API,
  local-mode behaviour, and a troubleshooting table (missing exporter package,
  missing ADC, permission denials, batching delay, org policy).
- `docs/gcp/README.md` — dashboard create/update/list, and the note that
  renaming the service or changing region means editing the filters first.

## What is still unproven

Everything cloud-side. The runbook's section 9 is the open item: no trace has
yet been opened in the explorer for a deployed run, no live subcollection read
from production Firestore, no dashboard created in `quanta-gradesync`. The
offline path is exercised by tests; the cloud path is exercised by a deploy that
has not happened yet. Until then this entry describes wiring that is built and
reviewed, not measured — and the next entry should carry the job id, the 32-hex
trace id and the dashboard name that prove it.
