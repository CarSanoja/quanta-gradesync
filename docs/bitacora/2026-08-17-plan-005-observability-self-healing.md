# Dev log — Plan 005: observability, forensic tracing and self-healing

**Date:** 2026-08-17
**Domain:** Planning
**Fulfills:** SOL-012
**Non-negotiable:** deterministic telemetry fully separated from the repairing agent; strict repair budgets; immutable audit trail; suite stays offline-green.

## Design stance

- The repairing agent can fix formats and retry calls — it can never rewrite the
  audit trail or mutate L3 without passing the existing gates. Telemetry is
  deterministic (typed spans, no LLM in the loop); healing is bounded (budgets).
- The requested `resilience/circuit_breaker.py` already exists as
  `core/harness/breakers.py` (batch anomaly breaker, cycle 004) — not duplicated;
  `core/resilience/` adds only the three new mitigation agents plus the dead-letter
  store. Budgets (`harness/budgets.py`) remain the single repair-cap authority.

## 1. Telemetry (`core/telemetry/`)

- `schemas/telemetry.py`: typed span model — name, trace/span/parent ids, stage,
  status, duration, and string→str/bool/int/float attribute map. Mandatory
  attribute keys as constants: `gen_ai.system`, `gen_ai.usage.tokens`,
  `agent.stage`, `evidence.span_match`.
- `tracer.py`: in-memory `Recorder` producing a span **tree** (children nest by
  parent span id, deterministic ordering). Trace context propagation: `trace_id`
  is generated at the webhook inside the `PubSubJobEvent` and flows through every
  stage and tool call; the recorder rides in `JobContext` (L1) and the finished
  tree is attached to the job record.
- `metrics_collector.py`: deterministic aggregation — per-stage count, error rate,
  latencies with **P95**, token totals from `gen_ai.usage.tokens` attributes.
- `audit_logger.py`: append-only forensic JSON log per job (local file / Firestore
  collection); writes only ever append — the healer cannot rewrite history.

## 2. Self-healing (`core/resilience/`)

- `dead_letter_store.py`: `DeadLetterStore` protocol + local/Firestore backends;
  records kind/target/reason/attempts with `max_attempts` (default 3).
- `repair_agent.py`: `SchemaRepairAgent` — bounded surgical repair of broken
  contract payloads using the exact Pydantic error and the strict schema; budget
  cap 2 (from `GRADESYNC_SCHEMA_REPAIR_ATTEMPTS`); on exhaustion the exam is
  escalated to the dead-letter store and isolated (never looped).
- `model_fallback.py`: `ModelFallbackController` — wraps a primary evaluator; on
  latency above `model_fallback_latency_seconds` (default 15) or transient API
  errors (timeout / resource-exhausted signatures) it retries that item once on
  the fallback evaluator (Gemini Flash) with a simplified prompt and **scales the
  returned confidence** by `model_fallback_confidence_factor` (default 0.9) so the
  existing confidence gate flags the item for review.
- `state_rollback.py`: partial-write rollback — when an SIS write fails mid-batch,
  failed record ids go to the dead-letter store as orphans and the checkpointed
  session remembers per-record statuses; the next execution window (Pub/Sub
  redelivery resuming at SYNC) retries **only the orphaned transactions**.

## 3. Integration points

- Webhook: generates `trace_id` into the event; JobRecord carries it.
- Runner: opens a root span per stage (`agent.stage`), records failures, and on
  job completion/failure persists the audit trail (span tree + record summary).
- GRADE: per-exam span (`gen_ai.system`, `gen_ai.usage.tokens` when the evaluator
  reports usage), `FaithfulnessVerification` span with `evidence.span_match`,
  evaluator wrapped by the fallback controller; contract violations flow through
  the repair agent into the dead-letter store with blast-radius isolation.
- SYNC: partial failures → orphan ids to DLQ; resume retries only orphans.
- Settings: `model_fallback_latency_seconds`, `model_fallback_confidence_factor`,
  `dead_letter_max_attempts`, `telemetry_audit_enabled`.

## 4. Tests planned

`tests/telemetry/` — span tree nesting and mandatory attributes; trace id
propagation from webhook to record; P95 and token aggregation; audit log
append-only immutability. `tests/resilience/` — repair budget (success on second
attempt; exhaustion escalates to DLQ, no third attempt); fallback triggers
(timeout, latency, transient error) with confidence scaling and pass-through on
health; partial SIS failure → DLQ orphans → resume retries only orphans and
completes; max-attempt orphans stay flagged for humans.

## 5. Documentation

Per the standing policy (and today's explicit instruction): all documentation from
now on is written in English, and the existing Spanish dev-log and requests
registry are translated in this cycle so the whole repository is English. Product
docs and README updated with the new guarantees.
