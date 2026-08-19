# Dev log — Architecture and flow: a cold run

**Date:** 2026-08-12
**Domain:** Technical architecture
**Status:** Implemented and verified (53/53 tests at the time; superseded by later cycles)

## The idea in one sentence

It is not a chat: it is a **typed conveyor belt**. An external event (an exam
upload) pushes a "job" through six stages, each stage talks to the next **only
through strict Pydantic contracts**, and a slower second plane runs in parallel,
improving the system's prompts without being able to cheat.

## Two-plane diagram

```text
          ┌──────────── HOT PLANE (per job, seconds/minutes) ────────────┐
Teacher ─► GCS ─► Pub/Sub ─► POST /webhooks/pubsub ─► JobRunner
uploads                            (token + idempotency)     │
scans                                                        ▼
          FETCH ─► GRADE ─► AUDIT ─► RISK ─► SYNC ─► OPTIMIZE ─► COMPLETED
            │        │         │       │      │        │
          staging  Gemini    Gemini   pure   gate +  goal      convergence
          files    3.5 Pro   3.5      stats  SIS/L3  checks +   tournaments
                             + L3     + L3   write    bounded    (cold plane
                             history         rework     trigger)
          └──────────────────────────────┬─────────────────┴──────────┘
                                         ▼
          ┌────────── COLD PLANE (periodic, self-improvement) ──────────┐
          CalibrationSet (human ground truth) ─► MAE/QWK/bias ─────────┐
          Proposer LLM proposes a new prompt ──────────────────────────┤
          Candidate is re-evaluated ─► AntiGamingValidator ─► accept?  │
          └─────────────────────────────────────────────────────────────┘
```

## Service cold start (once)

The FastAPI lifespan builds the `AppContainer`
(`src/autocurricula/api/dependencies.py`): it reads `Settings` and picks an
implementation per seam based on `local_mode`:

| Seam | Local (no credentials) | GCP |
|---|---|---|
| Exam files | `LocalStagingFetcher` | `GcsFetcher` |
| L2 vector memory | `LocalVectorMemory` (TF-IDF) | `FirestoreVectorMemory` |
| L3 persistent memory | `LocalPersistentStore` (JSON) | `FirestorePersistentStore` |
| SIS writes | `LocalSISConnector` (jsonl) | `HttpSISConnector` |
| Checkpoints | `LocalCheckpointStore` | `FirestoreCheckpointStore` |

Business logic is identical in both modes; only the transports change.

## Run stages

1. **Trigger.** Upload to the bucket → Pub/Sub → push to
   `POST /webhooks/pubsub` (`webhooks.py`). Validates the bearer token in
   constant time, decodes the envelope into a strict `PubSubJobEvent`, checks
   idempotency against the checkpoint store (`duplicate` → 200 without
   reprocessing), launches `runner.process()` in the background and answers
   `accepted` immediately.
2. **FETCH.** `JobCatalog.load_manifest(event)` loads the batch manifest
   (files, rubric, curriculum standard); the fetcher materializes files. Typed
   output: `ExamBatch` + `Rubric` + `CurriculumStandard`.
3. **GRADE.** The rubric is upserted into L2 and context is retrieved
   (top-5); `asyncio.gather` grades every submission concurrently with
   `AdkGradingEvaluator` (Gemini 3.5 Pro multimodal, output schema
   `GradingResult`, every score cites an `EvidenceSpan`; repair retry if it
   fails to parse).
4. **AUDIT.** Query with the ministry competencies → L2 → Gemini Flash maps
   criteria to competency codes: `covered_codes` vs `missing_codes`.
5. **RISK.** No LLM: loads episodic profiles from L3 and computes z-scores,
   trend, confidence collapse and missing-work rate → explainable
   `RiskAssessment`.
6. **SYNC.** `SISGradeRecord` → SIS connector; `persist_outcomes` writes back
   to L3 (`TermSnapshot` per student, `ClassCompetencySnapshot` per
   competency).
7. **OPTIMIZE.** Triggers a meta-optimizer cycle and marks `COMPLETED`.

After every stage: session + record checkpoint. Instance death → Pub/Sub
redelivers → the runner restores the session, skips `SUCCEEDED` stages and
continues (`runner.py`).

## Cold plane: self-evolution with a lock

`MetaOptimizerEngine.run_iteration`:

1. Evaluates the current variant against the `CalibrationSet` (human ground
   truth) → `CalibrationMetrics` (MAE, QWK, bias).
2. Proposer (Gemini Flash, strict `ProposalSchema`) proposes a mutation with
   justification.
3. The candidate is re-evaluated on the same ground truth.
4. `AntiGamingValidator`: rejects variance collapse, constant outputs and
   improvements without ground-truth contact.
5. Only if it passes: `PromptRegistry.register` promotes with a version bump
   (rollback available).

Semantics: the optimizer optimizes agreement with humans, not distribution
cosmetics.

## Semantics of the three memories

- **L1 — SessionMemory:** ephemeral per-job worktable, serializable to
  checkpoint.
- **L2 — VectorMemory:** "what is relevant now?" — rubrics and competencies by
  meaning.
- **L3 — PersistentStore:** "what do we remember about this student over
  time?" — episodic profiles and class snapshots; turns RISK into trajectory
  detection.

Governing principle: **every arrow in the diagram is a Pydantic model with
`extra=forbid`**. No agent invents fields; garbage explodes loudly, never
propagates silently.
