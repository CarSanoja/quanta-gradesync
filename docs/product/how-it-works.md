# How the GradeSync Engine Works — A Cold Run

| | |
|---|---|
| **Status** | Maintained — living document, updated with every implementation cycle |
| **Audience** | Engineers integrating, deploying, or extending the engine |
| **Last updated** | 2026-08-17 (Implementation 004 — agent harness) |
| **Related** | [Product Overview](product-overview.md) · [Root README](../../README.md) · [Dev Log (bitácora)](../bitacora/README.md) |

---

## Table of contents

1. [The core idea](#1-the-core-idea)
2. [System overview](#2-system-overview)
3. [Cold start: service boot and wiring](#3-cold-start-service-boot-and-wiring)
4. [The trigger: upload → Pub/Sub → webhook](#4-the-trigger-upload--pubsub--webhook)
5. [Zero-form intake: manifest resolution](#5-zero-form-intake-manifest-resolution)
6. [The pipeline, stage by stage](#6-the-pipeline-stage-by-stage)
7. [The memory hierarchy](#7-the-memory-hierarchy)
8. [Self-evolution: tournaments with a guardrail](#8-self-evolution-tournaments-with-a-guardrail)
9. [The agent harness](#9-the-agent-harness)
10. [Human review API](#10-human-review-api)
11. [Failure semantics and idempotency](#11-failure-semantics-and-idempotency)
12. [The type-safety philosophy](#12-the-type-safety-philosophy)
13. [Where things live](#13-where-things-live)

---

## 1. The core idea

The GradeSync Engine is **not a chat application**. It is a typed conveyor belt:
an external event (a batch of scanned exams landing in a bucket) pushes a *job*
through seven stages, every stage communicates with the next **only through strict
Pydantic contracts**, and a second, slower plane continuously improves the system's
prompts without ever being able to cheat.

Two planes run side by side:

- **The hot plane** — per job, seconds to minutes: fetch → grade → audit → risk →
  sync → verify → optimize. Deterministic orchestration with agentic islands.
- **The cold plane** — periodic, event-triggered: the self-evolution loop that
  rewrites the grading and auditing prompts under an anti-gaming guardrail.

## 2. System overview

```text
            ┌───────────────── HOT PLANE (per job, seconds/minutes) ─────────────────┐
Teacher ──► GCS bucket ──► Pub/Sub ──► POST /webhooks/pubsub ──► JobRunner
uploads                                  (token + idempotency)        │
scans                                                                 ▼
          FETCH ─► GRADE ─► AUDIT ─► RISK ─► SYNC ─► VERIFY ─► OPTIMIZE ─► COMPLETED
            │        │         │       │      │        │          │
         stage    Gemini    Gemini   pure   gate +  goal      convergence
         files    3.5 Pro   3.5      stats  SIS/L3  checks +   tournaments
                  + L2 ctx  Flash    + L3   write    bounded    (cold plane
                                     history         rework      trigger)
            └──────────────────────────────┬─────────────────┴──────────┘
                                           ▼
            ┌────────────── COLD PLANE (per trigger, self-improvement) ─────────────┐
            CalibrationSet (human ground truth) ──► MAE / QWK / bias ──────────────┐
            Proposer LLM proposes N prompt mutations ──────────────────────────────┤
            Every candidate re-evaluated on the SAME ground truth                  │
            AntiGamingValidator: variance collapse · constant output · GT contact  │
            Convergence loop: repeat until marginal gain < ε or budget exhausted   │
            └───────────────────────────────────────────────────────────────────────┘
```

## 3. Cold start: service boot and wiring

When the container starts on Cloud Run (`min-instances=1`, no cold starts), the
FastAPI lifespan builds the `AppContainer` (`src/autocurricula/api/dependencies.py`).
For every external seam, an implementation is selected from settings:

| Seam | Local mode (no credentials) | GCP mode |
|---|---|---|
| Exam files | `LocalStagingFetcher` (reads a staging directory) | `GcsFetcher` (downloads to tmp) |
| L2 vector memory | `LocalVectorMemory` (real TF-IDF index, stdlib only) | `FirestoreVectorMemory` (`find_nearest`, Vertex embeddings) |
| L3 persistent memory | `LocalPersistentStore` (JSON mirrors on disk) | `FirestorePersistentStore` |
| SIS writes | `LocalSISConnector` (append to `.jsonl`) | `HttpSISConnector` (POST + retries) |
| Checkpoints | `LocalCheckpointStore` (one JSON per job) | `FirestoreCheckpointStore` |
| Review queue | `LocalReviewStore` (JSON per item) | `FirestoreReviewStore` |
| Grading / auditing / proposer | deterministic local implementations | Gemini 3.5 Pro / Flash via ADK |
| Embeddings | hashing embedder (offline) | `text-embedding-005` (Vertex) |

Business logic is identical in both modes — only the transports change. This is why
the full test suite (107 tests at the time of writing) runs offline with zero GCP
credentials.

## 4. The trigger: upload → Pub/Sub → webhook

1. The school uploads scanned exams to the bucket; a bucket notification reaches
   Pub/Sub, which pushes the event to `POST /webhooks/pubsub`
   (`src/autocurricula/api/webhooks.py`).
2. The handler validates the bearer token in constant time (401/403 on failure),
   decodes the base64 envelope into a strict `PubSubJobEvent` (400 on malformed
   payloads — Pub/Sub does **not** retry client errors).
3. **Idempotency check**: if a checkpoint already exists for the job, the handler
   answers `duplicate` immediately, so Pub/Sub stops redelivering.
4. New jobs are launched as background tasks and the endpoint answers `accepted`
   right away — the ack is fast; the heavy work continues inside the instance.

## 5. Zero-form intake: manifest resolution

Nobody fills a per-assessment form. The catalog resolves each batch in order
(`core/orchestration/catalog.py` + `manifest_inference.py`):

1. **Explicit manifest** — a `batch.json` inside the batch prefix wins whenever it
   exists. An *invalid* manifest fails loudly; it is never silently replaced.
2. **Auto-inference by convention** — with no manifest, the engine infers the batch:

```text
<bucket>/
├── catalog-defaults.json              once per term, by pedagogical coordination:
│                                      { bindings: [ { subject, grade_level,
│                                        rubric, curriculum_standard } ] }
└── batches/
    └── 2026_Matematicas_10A_Parcial1/  {year}_{subject}_{class}_{assessment}
        ├── ana-torres.jpg               one file per student; the file stem is
        └── luis-gomez.pdf               the student id / submission id
```

Honesty rules: the lot-code subject and class must match the Pub/Sub event
attributes (a mismatch fails the job with the exact reason), the subject must have
a binding in `catalog-defaults.json`, and at least one gradable file
(jpg/jpeg/png/pdf/heic) must exist under the prefix. The system never guesses.

## 6. The pipeline, stage by stage

All seven stages checkpoint after completion; a resumed job skips stages already
`SUCCEEDED`.

**1. FETCH** — the catalog resolves the manifest; the fetcher materializes files to
local paths. Typed output: `ExamBatch` + `Rubric` + `CurriculumStandard`.

**2. GRADE** — the rubric is upserted into L2 and its context retrieved (top-k by
meaning). All submissions are graded **concurrently** through the
`GradingEvaluator` seam: Gemini 3.5 Pro, multimodal, with tools (`fetch_exam_files`,
`search_rubrics`), forced structured output (`GradingResult`), and an evidence-first
policy — every criterion score must cite an `EvidenceSpan` (page + verbatim quote)
or validation fails and one repair retry fires before a loud
`GradingValidationError`.

**3. AUDIT** — Gemini 3.5 Flash cross-references each result against the ministry
standard under a conservative policy (map only what evidence supports; unknown
codes are never invented). Output: competency mappings, `covered_codes`,
`missing_codes`.

**4. RISK** — deliberately **no LLM**. For each student the engine loads the
episodic profile from L3 and computes deterministic signals (z-scores on the
percentage history, negative trend slope, evidence-confidence collapse,
missing-submission rate). Output: an explainable `RiskAssessment` with drivers and
recommended interventions.

**5. SYNC (confidence-gated)** — records are partitioned per student by the
`ConfidenceGate`: a record auto-syncs only if its weakest criterion confidence is
at or above `GRADESYNC_CONFIDENCE_THRESHOLD` (default 0.85) **and** every criterion
cites evidence. Anything else is quarantined: it never touches the SIS or the L3
history; instead a `ReviewItem` is created carrying the exact page, the quoted
excerpt, the reasons, the document URI, and the proposed record.

**6. VERIFY (agentic closure)** — a goal verifier evaluates the job's mission with
five deterministic checks (every submission graded, audited, and risk-assessed; SIS
write clean; every quarantine accounted for) and runs a **bounded rework loop**:
quarantined submissions are re-graded by a *second-opinion* evaluator (Gemini Flash
instead of Pro in GCP mode). A submission that now clears the gate gets its review
item updated — new record, reasons, and rework notes — **but it stays `PENDING`**:
one-click approval remains the teacher's. The loop stops on convergence, on a
no-progress iteration, or at the `GRADESYNC_VERIFY_MAX_ITERATIONS` budget, and the
persisted `VerificationReport` separates `pending_human_approval` from
`unresolved_submission_ids` (genuinely needing human eyes).

**7. OPTIMIZE** — triggers the cold plane (below) for **both** evolving prompts —
grading and curriculum auditing — each running its own convergence loop.

## 7. The memory hierarchy

| Tier | Question it answers | Local | GCP | Lifetime |
|---|---|---|---|---|
| **L1** Session | "What is this job's working set?" | typed `SessionState`, serialized to checkpoints and **re-validated** on restore | same | one job |
| **L2** Vector | "What is relevant *right now*?" | real TF-IDF (smoothed IDF, sparse cosine, deterministic tie-break) | Firestore `find_nearest` + Vertex `text-embedding-005` | cross-job semantic retrieval |
| **L3** Managed | "What do we remember about this student *over time*?" | JSON mirrors | Firestore | persistent |

L3 stores **curated knowledge, not chat logs**: episodic student profiles
(`TermSnapshot` aggregates) and class competency snapshots, written only from
confirmed outcomes — a quarantined grade never pollutes history until approved.

## 8. Self-evolution: tournaments with a guardrail

Each optimizer (grading, auditor) runs a convergence loop of tournaments:

1. **Evaluate the incumbent** prompt variant against the human ground-truth
   `CalibrationSet` → MAE, quadratic weighted kappa, bias.
2. **Propose** `GRADESYNC_OPTIMIZER_CANDIDATES` (default 3) mutations — Gemini Flash
   with a strict `ProposalSchema` and escalating temperature per attempt (the local
   heuristic proposer rotates directives; both are real code paths).
3. **Re-evaluate every candidate** on the *same* ground truth. Identical candidates
   are deduplicated before evaluation.
4. **Gate with `AntiGamingValidator`**: rejects constant outputs, variance collapse
   (candidate score std below a floor of the ground-truth std without agreement
   improvement), and metrics that improved without full ground-truth contact.
5. **Promote only the best accepted candidate** (min MAE, tie-break higher QWK),
   with a version bump in the `PromptRegistry` (rollback available) and persistence
   to L3 with its report.
6. **Converge**: repeat until a cycle accepts nothing, the marginal improvement
   falls below `GRADESYNC_OPTIMIZER_CONVERGENCE_MIN_IMPROVEMENT`, or
   `GRADESYNC_OPTIMIZER_MAX_CYCLES` is exhausted.

The optimizer optimizes *agreement with humans*, never distribution cosmetics.

## 9. The agent harness

A domain-agnostic harness (`src/autocurricula/core/harness/`) separates governance
from the model — the model decides what to attempt; the harness decides what is
allowed to execute. It operates on generic concepts (`ToolAction`, risk levels,
budgets, thresholds), so recycling it into another agent means re-registering rules,
not rewriting domain code.

**Execution harness (runtime)**

- **Deterministic permission pipeline** — every external action passes
  `DENY > QUARANTINE > ALLOW` rules before any network call: a write targeting a
  student outside the batch manifest is denied in memory; an SIS write below the
  confidence threshold is diverted to quarantine.
- **Per-item budgets and blast-radius containment** — at most
  `GRADESYNC_HARNESS_MAX_CALLS_PER_ITEM` agent invocations per exam (schema-repair
  attempts bounded at 2, enforced at the LLM seam); an exam that exhausts its budget
  or raises is isolated and the rest of the batch continues. The gap surfaces in the
  verifier's `submissions_graded` check.
- **Faithfulness verifier** — when a page transcript exists (a `.txt` sidecar next
  to the scan), every cited `EvidenceSpan.quote` is checked for literal presence
  (whitespace/case-normalized). A hallucinated quote zeroes the criterion confidence,
  which the confidence gate then quarantines.

**Evaluation harness (offline)**

- **Composite objective gate** — on top of the anti-gaming validator, a prompt is
  promoted only if `QWK ≥ 0.85 ∧ MAE ≤ 0.4 ∧ |Bias| < 0.1` (scope-adjusted; the
  auditor scope skips the ill-defined QWK and relaxes bias). The variance-collapse
  sensor defaults to a 20% floor (`GRADESYNC_VARIANCE_COLLAPSE_RATIO`).
- **CI anti-regression gate** — the test suite runs the local deterministic
  evaluator over the golden fixtures and compares against a committed baseline
  (`tests/harness/golden_baseline.json`). Absolute production thresholds apply at
  runtime against the real evaluator; CI pins no-regression.

**Circuit breakers and governance**

- **Batch anomaly breaker** — if more than `GRADESYNC_BATCH_ANOMALY_THRESHOLD`
  (default 15%) of a batch lands in `REQUIRES_HUMAN_REVIEW`, automatic sync for the
  *entire* batch is suspended: every record goes to the review queue with the
  breaker reason attached. Working hypotheses: defective scan, wrong rubric, or
  model drift.
- **Provenance & decision ledger** — every SIS record (and every review item's
  proposed record) carries `Provenance{prompt_variant_id, prompt_version_sha,
  evidence_hashes, model_sha}`: a SHA-256 of the canonical prompt variant and of
  each cited evidence span. Any later audit can trace which prompt version and which
  cited fragment produced each grade.

## 10. Human review API

All endpoints require `Authorization: Bearer $GRADESYNC_PUBSUB_PUSH_TOKEN`.

| Method & path | Purpose |
|---|---|
| `GET /review/pending` | Quarantined items: page, cited excerpt, reasons, rework notes, proposed record |
| `POST /review/{review_id}/approve` | Writes the proposed record to the SIS, updates L3 history, marks approved (`409` if already decided) |
| `POST /review/{review_id}/dismiss` | Closes the item without writing |

Health: `GET /healthz` (liveness) and `GET /readyz` (settings + backend ping).

## 11. Failure semantics and idempotency

- **Idempotency at three levels**: webhook duplicate detection, runner short-circuit
  on `COMPLETED` checkpoints, and resume that skips `SUCCEEDED` stages.
- **At-least-once delivery is safe**: a redelivered event either finds the job
  complete (`duplicate`) or resumes exactly at the pending stage — no stage is ever
  recomputed after succeeding.
- **Loud failures**: any stage exception marks the job `FAILED` with the error in
  the `JobRecord`; nothing degrades silently.
- **Checkpoints** persist both the `JobRecord` and the full `SessionState` after
  every stage (local JSON or Firestore).

## 12. The type-safety philosophy

Every arrow in the architecture diagram is a Pydantic model with `extra="forbid"`.
Agents cannot invent fields, stages cannot degrade contracts, and any LLM output
that fails to parse is repaired once and then fails loudly — it never propagates
silently into the SIS. This single principle is what makes a heterogeneous fleet of
models, tools, and stores composable and auditable.

## 13. Where things live

```text
src/autocurricula/
├── config/              settings + lazy GCP client factories
├── schemas/             strict Pydantic contracts (incl. review, verification)
├── tools/               GCS fetcher, SIS connector, vector search tools
├── agents/              grading, auditor, risk, meta-optimizer + factories
│   └── prompts/         versioned prompt variants (seeds for every scope)
├── core/memory/         L1 session, L2 vector (+embeddings), L3 persistent
├── core/harness/        permission gate, budgets, faithfulness, breakers, provenance
│   └── eval_harness/    objective gate + golden-dataset runner
├── core/evolution/      calibration, prompt registry, anti-gaming, tournament engine
├── core/review/         confidence gate, review store, approval service
├── core/orchestration/  catalog + inference, pipeline graph, runner, verifier
└── api/                 FastAPI app, Pub/Sub webhook, review API
```

Test suites mirror the domains under `tests/` (`orchestration`, `review`,
`calibration`, `core_memory`, `api`, `benchmarks`) and run fully offline.
