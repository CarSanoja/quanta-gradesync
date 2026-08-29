# Resetting the demo, and why it is not one line

## The fast way

```bash
gcloud config configurations activate default
GOOGLE_ACCESS_TOKEN=$(gcloud auth print-access-token) \
  .venv/bin/python scripts/reset_demo_state.py --yes --fast
```

`--fast` hands the walk to Google — `gcloud firestore bulk-delete` runs the
deletion server-side and returns as soon as the operation is accepted — then
sweeps whatever the operation could not see. On a full three-section run that is
seconds instead of minutes.

Add `--now` to skip the wait described below. Add `--adc` on a machine with no
gcloud profile to borrow.

## Why there is no DROP

Firestore has no `DROP TABLE` and no delete-collection call. Deleting a
collection means deleting every document in it, and from a client that is one
round trip per document. Two things made that slow, and both are fixed:

- **The subcollection probe.** A parent that exists only to hold a subcollection
  is invisible to a query, and `audit/{job}/live` is exactly that — streaming
  left thousands of live events behind on every reset. So each document is asked
  for its children, which is a round trip each: measured on a real run, listing
  525 events took 2.1 seconds and probing them took 49 seconds for 200 of them.
  The probes now run in parallel.
- **The bucket.** One delete per object put 348 scans past a minute. Also
  parallel now.

`--fast` avoids the walk entirely for the common case. The walk stays because
bulk-delete is eventually consistent: anything written after its snapshot
survives, and something has to sweep that.

## Why it sometimes waits

By default the reset waits until nothing has written for thirty seconds.

Deleting under a running batch cannot come out clean. The job keeps writing after
the wipe finishes, so the console fills back up and the reset looks broken when it
was only racing. This happened six times in one afternoon on 2026-08-29, and each
time the answer was to run it again later.

Purging the push subscription stops *new* deliveries but not a message already
inside a container:

```bash
gcloud pubsub subscriptions seek exam-batch-ingest-push \
  --time="$(date -u +%Y-%m-%dT%H:%M:%SZ)" --project quanta-gradesync
```

The only thing that stops a batch already in flight is the batch ending, or
killing the instances:

```bash
gcloud run services update autocurricula-gradesync \
  --region us-central1 --project quanta-gradesync \
  --revision-suffix=stop-$(date -u +%H%M%S)
```

That rolls a new revision from the same image and drains the old instances. It
patches, so environment variables and secrets survive.

## What is deliberately kept

Two objects in `gs://quanta-gradesync-exams` are not demo state and are never
deleted:

- `catalog-defaults.json` — the rubric binding manifest inference reads at the
  bucket root. Without it no batch starts.
- `demo-source/` — the sixteen scans the judges' "Load sample batch" button
  copies from. Without it step 3 of the judge guide does nothing.

## Verifying

The script prints what it deleted, but the honest check is to look twice:

```bash
GOOGLE_ACCESS_TOKEN=$(gcloud auth print-access-token) .venv/bin/python - <<'PY'
import os, time
from google.oauth2.credentials import Credentials
from google.cloud import firestore
db = firestore.Client(project="quanta-gradesync",
                      credentials=Credentials(token=os.environ["GOOGLE_ACCESS_TOKEN"]))
r = lambda: sorted(c.id for c in db.collections())
a = r(); time.sleep(20); b = r()
print("now:", a or "EMPTY", "| after 20s:", b or "EMPTY")
PY
```

If a collection reappears, a batch is still running. That is the signal, not a
failure of the reset.
