# Dev log — Implementation 005: observability, forensic tracing, self-healing

**Date:** 2026-08-17
**Domain:** Implementation
**Fulfills:** Plan 005 (SOL-012)
**Verification:** `.venv/bin/pytest -q` → **158 passed / 0 failed** (was 139; +19 tests). Clean compile, no comments, every file ≤ 200 lines, suite fully offline.

## Telemetry — deterministic, fully separated from the repairing agent

- `schemas/telemetry.py`: typed span model with mandatory attribute keys
  (`gen_ai.system`, `gen_ai.usage.tokens`, `agent.stage`, `evidence.span_match`).
- `core/telemetry/tracer.py`: in-memory `Recorder` producing a creation-ordered
  span **tree** (children nested by parent id; error spans capture `error.type`
  and re-raise). `trace_id` is generated at the webhook inside the
  `PubSubJobEvent` and flows through every stage and span.
- `core/telemetry/metrics_collector.py`: per-stage counts, error rates,
  nearest-rank **P95** latency and token totals.
- `core/telemetry/audit_logger.py`: append-only forensic JSONL per job (local)
  / Firestore subcollection (GCP). The runner persists the full span tree plus
  a metrics snapshot on completion *and* on failure; an audit write failure
  never fails the job.
- The runner opens one span per pipeline stage (`agent.stage`), and the grade
  guard opens one span per exam (`gen_ai.system`, model, student) with a child
  `FaithfulnessVerification` span carrying `evidence.span_match`.

## Self-healing — bounded, never loopy

- `core/resilience/repair_agent.py`: `SchemaRepairAgent` with a strict budget
  (1 call + 2 retries); exhaustion raises `RepairBudgetExhausted` and the exam
  is dead-lettered and isolated — never retried a third time.
- `core/resilience/model_fallback.py`: `FallbackEvaluator` — on timeout,
  resource-exhausted (429) or latency beyond the threshold, the item is retried
  once on the fallback model (Gemini Flash via the existing second-opinion
  factory) and the returned confidences are scaled by 0.9 so the confidence
  gate flags it for review.
- `core/resilience/dead_letter_store.py`: dead-letter queue (pending / resolved
  / exhausted) with local and Firestore backends and `max_attempts`.
- `core/resilience/state_rollback.py`: partial SIS failures stash the merged
  per-record result in the session, orphaned ids go to the dead letter, and the
  next execution window (Pub/Sub redelivery resuming at SYNC) retries **only
  the orphans**; exhausted orphans are never retried and stay flagged for
  humans; resolved orphans are closed.
- Safety guarantees honored: the healer can retry and reformat but never
  rewrites the append-only audit trail, and L3 writes still pass the same gates.

## Issues found and fixed during verification (by the tests themselves)

1. Span ordering: children were recorded before their parents (completion
   order) — the recorder now keeps creation order.
2. Percentile used `round` instead of standard nearest-rank `ceil`.
3. Rollback originally depended on `previous` alone: with pending orphans the
   rule is now *retry only the orphans* regardless of prior state, and prior
   successes travel in the checkpointed session.
4. Resolved orphans stayed `pending` forever — added `resolve()`.
5. The e2e test's partial connector physically wrote records it was about to
   report as failed — fixed the fixture so the ledger reflects accepted writes.

## New tests (19)

- `tests/telemetry/` (7): nesting and tree, error spans, mandatory attributes,
  deterministic ids, nearest-rank percentile, per-stage metrics, append-only
  audit.
- `tests/resilience/` (12): repair budget success/exhaustion/attempt-index,
  fallback on timeout/429/latency with confidence scaling, healthy pass-through,
  no-fallback reraise; orphan recording, retry-only-orphans, exhausted
  exclusion, end-to-end failed → resume → completed with exactly one write per
  student.

## Documentation

Per the standing English-only policy: cycle records written in English and the
existing Spanish dev log and requests registry translated in this same cycle.
README, `.env.example` and `docs/product/` updated with the new subsystems.
