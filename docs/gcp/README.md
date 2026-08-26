# GCP artifacts

Committed Google Cloud configuration that is part of the deployment, not a
screenshot of it. Everything here is applied with `gcloud`; nothing is
hand-clicked in the console.

| File | What it is |
|---|---|
| [`monitoring-dashboard.json`](monitoring-dashboard.json) | Cloud Monitoring dashboard for the Cloud Run service `autocurricula-gradesync` (`us-central1`) |

## Import the monitoring dashboard

```bash
gcloud monitoring dashboards create \
  --project=quanta-gradesync \
  --config-from-file=docs/gcp/monitoring-dashboard.json
```

The command prints the generated dashboard name
(`projects/<number>/dashboards/<id>`). Keep it: updating the committed file
later is an update, not a second create, or the project ends up with duplicates.

```bash
gcloud monitoring dashboards update projects/<number>/dashboards/<id> \
  --project=quanta-gradesync \
  --config-from-file=docs/gcp/monitoring-dashboard.json
```

List what exists and open it in the console:

```bash
gcloud monitoring dashboards list --project=quanta-gradesync \
  --format="table(name,displayName)"
```

https://console.cloud.google.com/monitoring/dashboards?project=quanta-gradesync

## What the dashboard shows

| Widget | Metric type |
|---|---|
| Request count by response class | `run.googleapis.com/request_count` (rate, grouped by `response_code_class`) |
| Request latency p95 | `run.googleapis.com/request_latencies` (p95 of the distribution) |
| Container instance count by state | `run.googleapis.com/container/instance_count` (grouped by `state`) |
| Container CPU utilization p99 | `run.googleapis.com/container/cpu/utilizations` |
| Container memory utilization p99 | `run.googleapis.com/container/memory/utilizations` |
| Service logs | Logs panel filtered to `cloud_run_revision` / `autocurricula-gradesync` |

These are platform metrics that Cloud Run emits on its own: they are populated
whether or not the service exports OTel telemetry. The application-level signals
(per-agent spans, LLM exchanges, token accounting) live in Cloud Trace and in
the live event stream — see
[`docs/runbooks/observability.md`](../runbooks/observability.md).

The dashboard is pinned to service `autocurricula-gradesync` in `us-central1`.
Deploying under a different service name or region means editing the `filter`
strings in the JSON before importing.

## Permissions

Creating or updating a dashboard requires `roles/monitoring.dashboardEditor` (or
`roles/monitoring.editor`) on `quanta-gradesync` for the identity running
`gcloud`. It is an operator action, not something the runtime service account
does.
