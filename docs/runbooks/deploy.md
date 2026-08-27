# Runbook — deploying to Cloud Run

One command builds, pushes and deploys. This page exists because the command
alone is not the whole truth: some settings are rewritten on every deploy and
some survive it, and knowing which is which is the difference between a
working service and the stall documented as finding 6 in
[`docs/reports/deploy-2026-08-19.md`](../reports/deploy-2026-08-19.md).

| | |
|---|---|
| Project | `quanta-gradesync` |
| Service | `autocurricula-gradesync`, `us-central1` |
| URL | https://autocurricula-gradesync-236mcbrtra-uc.a.run.app |
| Build identity | `gradesync-builder@quanta-gradesync.iam.gserviceaccount.com` |
| Runtime identity | `autocurricula-runner@quanta-gradesync.iam.gserviceaccount.com` |
| Config | [`cloudbuild.yaml`](../../cloudbuild.yaml) |

## 1. Authenticate

This project uses a gcloud configuration of its own, so deploying never
disturbs whatever account is active for other work:

```bash
export CLOUDSDK_CONFIG=$HOME/.gcloud-gradesync
gcloud auth login          # interactive; the session expires every few days
gcloud config set project quanta-gradesync
```

If `gcloud` answers `Reauthentication failed. cannot prompt during
non-interactive execution`, that is this step, not a broken deploy.

## 2. Deploy

```bash
export CLOUDSDK_CONFIG=$HOME/.gcloud-gradesync
gcloud builds submit . \
  --config=cloudbuild.yaml \
  --substitutions=SHORT_SHA=$(git rev-parse --short HEAD)
```

Every substitution has a working default, so that command is complete on its
own. Override one only to change that one thing:

```bash
--substitutions=SHORT_SHA=$(git rev-parse --short HEAD),_MIN_INSTANCES=1
```

## 3. What a deploy rewrites, and what it does not

This is the part that bites.

**Rewritten every time, from `cloudbuild.yaml`.** The deploy step passes
`--set-env-vars`, which *removes every existing environment variable first*.
So any value changed at runtime with `gcloud run services update
--update-env-vars` lives only until the next deploy. A value that must survive
belongs in the substitutions, not in a one-off update.

The same is true of every flag the step passes explicitly:
`--min-instances`, `--max-instances`, `--timeout`, `--memory`,
`--no-cpu-throttling`, `--service-account`, `--allow-unauthenticated`,
`--set-secrets`.

**Kept from the running service.** `gcloud run deploy` patches an existing
service: anything the command does not mention keeps its current value. That
is why settings applied once by hand — an IAM binding, an ingress rule — do
not need repeating. It is also why a missing flag can hide for months: the
service keeps doing the right thing while the repository no longer says how.

`--no-cpu-throttling` was in exactly that position until 2026-08-27. It was
applied by hand on 2026-08-19 and survived every deploy since, so nothing
looked wrong, but a clone of this repository could not have reproduced a
service that works. It is now in `cloudbuild.yaml`, and
`tests/deploy/test_cloudbuild_config.py` fails if it leaves again.

**Why that flag is not optional.** The webhook acknowledges the Pub/Sub push
immediately and runs the pipeline in a background task. With request-scoped
CPU, Cloud Run freezes that task the moment the response is sent — and because
the delivery was already acknowledged, Pub/Sub never retries. The job stops
at `fetched` and stays there. The service looks healthy; the work never
happens.

## 4. Settings that are deliberate

| Substitution | Default | Why |
|---|---|---|
| `_MIN_INSTANCES` | `0` | Scale to zero. Raise to `1` for a demo or a recording, then put it back — with CPU always allocated, a warm instance bills continuously. |
| `_MAX_INSTANCES` | `2` | Caps spend and keeps concurrent batches inside the Vertex quota. |
| `_MODEL_CONCURRENCY` | `16` | Measured on the 36-exam batch: drop→completed ≈ 150 s. Lower it if Vertex starts returning 429. |
| `_TELEMETRY_CAPTURE_CONTENT` | `true` | Records prompts and responses. Set to `false` for a school whose data rules forbid it — see [`observability.md`](observability.md). |
| `_GEMINI_LOCATION` | `global` | Gemini 3.x is only served from `global` on Vertex. A regional value fails at the first model call. |

## 5. Verify the deploy

```bash
export CLOUDSDK_CONFIG=$HOME/.gcloud-gradesync
SERVICE=https://autocurricula-gradesync-236mcbrtra-uc.a.run.app

# the revision that took traffic, and the settings that matter
gcloud run services describe autocurricula-gradesync \
  --region=us-central1 --project=quanta-gradesync \
  --format="value(status.latestReadyRevisionName,
    spec.template.metadata.annotations['run.googleapis.com/cpu-throttling'],
    spec.template.metadata.annotations['autoscaling.knative.dev/minScale'])"

# the service answers (Google Frontend reserves /healthz on *.run.app — use /readyz)
curl -s -o /dev/null -w '%{http_code}\n' $SERVICE/readyz

# the static bundle actually shipped: pip installs it via MANIFEST.in globs,
# so a new asset that was never added to a package list still needs checking
for a in teacher.css teacher-screens.css teacher-review.css teacher-dialogs.css \
         teacher.js teacher-batch.js teacher-routing.js; do
  printf '%s %s\n' "$(curl -s -o /dev/null -w '%{http_code}' $SERVICE/teacher/assets/$a)" "$a"
done
```

`cpu-throttling` must read `false`. Every asset must read `200`; a `404` means
the whitelist in `src/autocurricula/api/teacher.py` is missing the file, and a
`200` that serves stale bytes is not possible — `/teacher` is sent `no-store`
and its assets `no-cache, must-revalidate`.

Then open `/teacher` and `/console` and send one small batch end to end.

## 6. Roll back

Traffic can move to any revision that is still there, with no rebuild:

```bash
gcloud run services update-traffic autocurricula-gradesync \
  --region=us-central1 --project=quanta-gradesync \
  --to-revisions=<previous-revision>=100
```

List the candidates with `gcloud run revisions list --service
autocurricula-gradesync --region us-central1`. Rolling back traffic restores
that revision's environment as well, because a revision is immutable.

## 7. Token rotation

The push token is a Secret Manager secret (`gradesync-push-token`) mounted at
deploy time, never a literal in this repository. Rotating it is two changes,
not one: add a secret version, **and** update the Pub/Sub push endpoint, whose
query string carries the same token.

```bash
gcloud secrets versions add gradesync-push-token --data-file=-
gcloud pubsub subscriptions update exam-batch-ingest-push \
  --push-endpoint="$SERVICE/webhooks/gcs?token=<new-token>" \
  --push-auth-service-account=<oidc-sa> \
  --push-auth-token-audience="$SERVICE"
```

The audience must stay pinned to the service URL without the query string:
the default audience includes it, which is what made every delivery 403 on
2026-08-19.
