# Runbook — observability: traces, live events, metrics

How to switch on the three observability layers in GCP mode, verify each one,
and turn payload capture off when the data-sovereignty rules of a school forbid
it. Nothing here changes grading behaviour: every layer is a read path.

| Layer | Where it lands | Who reads it |
|---|---|---|
| 1. Native OTel export | Cloud Trace (`telemetry.googleapis.com`), Cloud Logging | Engineer debugging a job after the fact |
| 2. Live events | Firestore `audit/{job_id}/live` (local: `{local_data_dir}/live/{job_id}.jsonl`) | `GET /jobs/{job_id}/live` and the Mission control view of `/console` |
| 3. Metrics | Cloud Monitoring, rendered by [`docs/gcp/monitoring-dashboard.json`](../gcp/monitoring-dashboard.json) | On-call, capacity review |

Every job runs under a deterministic Cloud Trace trace id derived from its own
`trace_id` (`core/telemetry/trace_ids.py`: identity when the id is already
32 hex characters, otherwise the first 32 hex of its SHA-256). That is the seam
that makes a job id enough to find the trace — no id lookup table, no console
hunting.

## 1. Prerequisites

| Requirement | Value in this project |
|---|---|
| GCP project | `quanta-gradesync` |
| Cloud Run service | `autocurricula-gradesync` in `us-central1` |
| Runtime service account | `autocurricula-runner@quanta-gradesync.iam.gserviceaccount.com` |
| Python dependency | `opentelemetry-exporter-otlp-proto-http` (declared in `pyproject.toml`) |
| ADK | `google-adk` 2.7.0 — every LLM call already emits a `call_llm` span |

## 2. One-time: API and IAM

Enable the Telemetry API (the OTLP endpoint the ADK exporters push to) plus the
two APIs the other layers use:

```bash
gcloud services enable \
  telemetry.googleapis.com \
  monitoring.googleapis.com \
  logging.googleapis.com \
  --project=quanta-gradesync
```

Grant the runtime service account the three write roles. It needs nothing else
for observability — no read roles, no project-level editor:

```bash
SA=autocurricula-runner@quanta-gradesync.iam.gserviceaccount.com

for ROLE in roles/telemetry.tracesWriter roles/monitoring.metricWriter roles/logging.logWriter; do
  gcloud projects add-iam-policy-binding quanta-gradesync \
    --member="serviceAccount:${SA}" \
    --role="${ROLE}"
done
```

Verify the bindings landed:

```bash
gcloud projects get-iam-policy quanta-gradesync \
  --flatten="bindings[].members" \
  --filter="bindings.members:autocurricula-runner@quanta-gradesync.iam.gserviceaccount.com" \
  --format="table(bindings.role)"
```

Running the pipeline from a workstation instead of Cloud Run exports under the
ADC identity, so that identity needs the same three roles (or one of the broader
roles that contains them).

## 3. Deploy flags

`cloudbuild.yaml` sets the four telemetry flags on every deploy, each from a
build substitution so the deploy carries the value the build was given:

| Substitution | Env var | Default |
|---|---|---|
| `_TELEMETRY_LIVE` | `GRADESYNC_TELEMETRY_LIVE_ENABLED` | `true` |
| `_TELEMETRY_CLOUD_TRACE` | `GRADESYNC_TELEMETRY_CLOUD_TRACE_ENABLED` | `true` |
| `_TELEMETRY_CLOUD_METRICS` | `GRADESYNC_TELEMETRY_CLOUD_METRICS_ENABLED` | `true` |
| `_TELEMETRY_CAPTURE_CONTENT` | `GRADESYNC_TELEMETRY_CAPTURE_CONTENT` | `true` |

To flip one without a rebuild:

```bash
gcloud run services update autocurricula-gradesync \
  --project=quanta-gradesync --region=us-central1 \
  --update-env-vars=GRADESYNC_TELEMETRY_CAPTURE_CONTENT=false
```

**That flip lives only until the next deploy.** The deploy step uses
`--set-env-vars`, which replaces the whole environment of the service, so the
next CI build restores whatever the substitutions say. A value that must
survive deploys has to be changed at the source — override the substitution on
the build:

```bash
gcloud builds submit --config=cloudbuild.yaml \
  --substitutions=_TELEMETRY_CAPTURE_CONTENT=false
```

or change its default in `cloudbuild.yaml` so every automatic build carries it.

Cloud trace and metric export are no-ops in local mode
(`GRADESYNC_LOCAL_MODE=true`): nothing leaves the machine even with the flags
left at their defaults. The exporters are installed together, so
`GRADESYNC_TELEMETRY_CLOUD_METRICS_ENABLED=true` only has an effect while
`GRADESYNC_TELEMETRY_CLOUD_TRACE_ENABLED=true` — turning trace export off turns
metric export off with it.

## 4. Verify a trace

The trace id is deterministic, so it is computed from the job's `trace_id`
without touching Cloud Trace:

```bash
.venv/bin/python - <<'PY'
from autocurricula.core.telemetry.trace_ids import cloud_trace_id, cloud_trace_url

trace_id = "e2e-2026-08-19-matematicas-10a-parcial1"
print(cloud_trace_id(trace_id))
print(cloud_trace_url("quanta-gradesync", trace_id))
PY
```

Open the printed URL, or build it by hand:

```text
https://console.cloud.google.com/traces/list?project=quanta-gradesync&tid=<32hex>
```

The console renders the same link per job, so an operator never has to run the
snippet above.

What a healthy trace looks like: every span of the job shares the deterministic
trace id and hangs off a synthetic job parent (a non-recording context, so the
parent itself is never exported and the `Stage_<name>` spans are what the
explorer lists at the top). Under each stage sit the
`Grading_<submission_id>` spans (attributes `student_id`, `gen_ai.model`) with
`ArmorScreen` and `FaithfulnessVerification`
children, and — nested under the grading spans — the ADK `call_llm` spans
carrying `gcp.vertex.agent.llm_request` / `gcp.vertex.agent.llm_response`,
`gen_ai.request.model`, `gen_ai.usage.input_tokens`,
`gen_ai.usage.output_tokens` and `gen_ai.response.finish_reasons`. A denied tool
action appears as a `CapabilityDenied` span with `agent.id` and
`agent.principal`.

Logs are correlated to the trace through the
`logging.googleapis.com/trace` field, so the Trace detail view shows the log
lines of that job inline. To read them directly:

```bash
gcloud logging read \
  'resource.type="cloud_run_revision"
   resource.labels.service_name="autocurricula-gradesync"
   trace="projects/quanta-gradesync/traces/<32hex>"' \
  --project=quanta-gradesync --limit=50 --format=json
```

Export is batched, so spans surface a few seconds after they close. An empty
Trace explorer immediately after a run is not yet a failure — reload before
concluding anything.

Without a Cloud Trace seat, the same tree is readable from `GET
/jobs/{job_id}/trace` and from the **Post-run trace** tab of Mission control,
which lays it out as `Pipeline stages`, `What ran, and how long it took` (the
span tree itself), `Per-stage totals` and `Audit records written`. The `spans`
column of `Per-stage totals` counts spans, not model calls — a grading span with
its armor and faithfulness children contributes several spans and a different
number of `call_llm` exchanges.

## 5. Read live events

Live events are the streaming layer: one document per span start, span end and
LLM exchange, written while the job is still running.

- Firestore path: `audit/{job_id}/live/{seq:06d}` — collection name follows
  `GRADESYNC_FIRESTORE_AUDIT_COLLECTION`, `seq` is per-job monotonic from `1`,
  so lexical document order is chronological order.
- API: `GET /jobs/{job_id}/live?after=<seq>&limit=<n>` (same
  `Authorization: Bearer $GRADESYNC_PUBSUB_PUSH_TOKEN` as every other endpoint).
  The response carries `cloud_trace_id` / `cloud_trace_url`, the current
  `stage`, `settled` (the job reached `completed` or `failed`), `next_after` to
  poll with, and the `events` themselves.
- UI: the Mission control view of `/console`, three tabs over the same stream.
  **Fleet activity** — the fleet board (each agent card is a button that filters
  the ticker to that agent), the event ticker, and the payload drawer, whose
  attribute rows carry plain-English labels rather than raw span keys.
  **Reasoning per student** — one card per student, each step opening the exact
  event that produced it back on Fleet activity. **Post-run trace** — the
  persisted span tree, where a span row opens its own attributes. Beside them,
  an Open-in-Cloud-Trace link and `Export live events (.jsonl)`, which exports
  exactly what the API returned.
- A stage-level span carries no `agent_id` (it belongs to the stage, not to any
  one agent), so the per-agent totals on the fleet board legitimately add up to
  less than the header totals. That gap is not a lost event.

Read them from the command line:

```bash
curl -sS -H "Authorization: Bearer $GRADESYNC_PUBSUB_PUSH_TOKEN" \
  "https://autocurricula-gradesync-236mcbrtra-uc.a.run.app/jobs/<job-id>/live?after=0&limit=500" \
  | .venv/bin/python -m json.tool | head -60
```

An unknown job id answers `404 no job '<id>'` (the endpoint reads the checkpoint
record first), so an empty `events` list always means "this job produced no live
events", never "wrong id".

Straight from Firestore, bypassing the API:

```bash
.venv/bin/python - <<'PY'
from google.cloud import firestore

job = "<job-id>"
client = firestore.Client(project="quanta-gradesync")
events = client.collection("audit").document(job).collection("live").stream()
for doc in events:
    e = doc.to_dict()
    print(e["seq"], e["kind"], e["name"], e.get("agent_id"), e["status"])
PY
```

In local mode the same events are appended, one JSON object per line, to
`{GRADESYNC_LOCAL_DATA_DIR}/live/{job_id}.jsonl` — nothing is written to
Firestore and nothing is exported to Cloud Trace:

```bash
wc -l .local_data/live/*.jsonl
.venv/bin/python -m json.tool < <(head -1 .local_data/live/<job-id>.jsonl)
```

Live events sit under the audit document of the job, but Firestore does **not**
cascade: deleting `audit/{job_id}` leaves every document under
`audit/{job_id}/live/{seq}` in place, still readable by a direct collection
read. Erasing a job means deleting its subcollections explicitly — `events`
**and** `live` — before (or instead of) the parent document:

```bash
.venv/bin/python - <<'PY'
from google.cloud import firestore

job = "<job-id>"
client = firestore.Client(project="quanta-gradesync")
parent = client.collection("audit").document(job)
for subcollection in ("events", "live"):
    for doc in parent.collection(subcollection).stream():
        doc.reference.delete()
parent.delete()
PY
```

The cleanup step in [`e2e-gcp-run.md`](e2e-gcp-run.md) runs the same loop.

## 6. Data sovereignty: payload capture

`GRADESYNC_TELEMETRY_CAPTURE_CONTENT` is the switch a school's DPO can be shown.

| Value | Effect |
|---|---|
| `true` (default) | Prompt and response excerpts are attached to live events and LLM spans, truncated at `GRADESYNC_TELEMETRY_PAYLOAD_MAX_CHARS` (`truncated: true` marks a cut) |
| `false` | No prompt or response text is recorded anywhere: spans, live events and logs keep names, timings, token counts, model ids, armor verdicts and permission decisions only |

Turning capture off does not blind the fleet board — the structure of the run
(which agent, which stage, which student, how long, how many tokens, what
verdict) is metadata, not content. It only removes the payload drawer's text.

Lowering `GRADESYNC_TELEMETRY_PAYLOAD_MAX_CHARS` is the middle setting: enough
of the exchange to debug a bad grade, not enough to carry a full manuscript
transcript into telemetry storage.

Two independent reasons that no page image ever reaches telemetry: the ADK
request attribute excludes inline bytes, and the excerpts are text-only and
capped.

## 7. Metrics and the dashboard

`GRADESYNC_TELEMETRY_CLOUD_METRICS_ENABLED=true` installs the ADK OTLP metric
reader (`get_gcp_exporters(enable_cloud_metrics=True)`), which pushes on a
periodic interval to `telemetry.googleapis.com`. The committed dashboard covers
the Cloud Run platform metrics — import instructions in
[`docs/gcp/README.md`](../gcp/README.md):

```bash
gcloud monitoring dashboards create \
  --project=quanta-gradesync \
  --config-from-file=docs/gcp/monitoring-dashboard.json
```

Platform metrics (request count, latency, instances, CPU, memory) arrive with or
without the OTel export; the agent-level metrics arrive only while the flag is
on and the runtime SA can write them.

## 8. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Log line about `opentelemetry-exporter-otlp-proto-http` not installed, no spans and no metrics | The OTLP HTTP exporter package is missing from the image | It is declared in `pyproject.toml`; rebuild the container rather than pip-installing into a running revision |
| `DefaultCredentialsError` or "Cannot determine GCP Project" at startup | No ADC on a workstation, or the metadata identity has no project | `gcloud auth application-default login`, or set `GRADESYNC_GCP_PROJECT_ID` explicitly |
| `PERMISSION_DENIED` exporting spans or metrics | Missing role on the runtime SA, or `telemetry.googleapis.com` not enabled | Re-run section 2 and confirm with `gcloud projects get-iam-policy` |
| Trace explorer empty right after a run | Batched export | Wait a few seconds, then reload; check the log for exporter errors before re-running |
| Trace exists but has no `call_llm` spans | The run was local mode (scripted evaluators, no Gemini calls) | Set `GRADESYNC_LOCAL_MODE=false` with real credentials |
| `call_llm` spans exist but carry no payload attributes | `GRADESYNC_TELEMETRY_CAPTURE_CONTENT=false` (it sets ADK's own `ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS=false`), or that ADK variable was set in the environment | Set the project flag, and check the revision for a stray `ADK_*` override |
| `GET /jobs/{id}/live` returns `count: 0` mid-run | `GRADESYNC_TELEMETRY_LIVE_ENABLED=false`, or `after` is already past the last event | Check the flag, then re-query with `after=0` |
| `GET /jobs/{id}/live` answers `404 no job` | The id is a `trace_id` (or a typo), not the job id of a checkpoint record | Take the id from `GET /console` or from the webhook response |
| `502 live feed unavailable` | Firestore (or the local `live/` directory) could not be read | Check the runtime SA's Firestore access; the message carries the underlying error |
| Console mission control shows nothing but the job finished | Live events are per job; a job that never started (rejected push, bad token) has none | Check the webhook response and the Cloud Run request log first |
| Nothing at all in Cloud Trace, everything in the local JSONL | The service is in local mode | `GRADESYNC_LOCAL_MODE=false` on the revision |

Org policy note: this project's public-access policy already forces
authenticated calls to the console and the API. It does not affect telemetry
export, which is an outbound call from the service to Google APIs under the
runtime service account.

## 9. Pending production verification

The three layers are implemented and covered by the offline suite. As of
2026-08-25 they have **not** yet been exercised against the deployed revision:
the trace explorer check (section 4), the live-event read from Firestore
(section 5) and the dashboard import (section 7) are all pending the next
production deploy. Record the results here — with the job id, the 32-hex trace
id and the dashboard name — once that run happens; do not assume the numbers.
