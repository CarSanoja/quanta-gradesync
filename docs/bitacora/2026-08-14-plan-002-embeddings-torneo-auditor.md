# Dev log — Plan 002: semantic embeddings + candidate tournament + auditor evolution

**Date:** 2026-08-14
**Domain:** Planning
**Solves:** Gaps 1–3 of Audit 001
**Non-negotiable:** the full suite keeps running offline, without credentials.

## 1. Injectable semantic embeddings in L2

- New `core/memory/embeddings.py`: `Embedder = Callable[[str], list[float]]`.
  - `HashingEmbedder`: the current feature hashing (deterministic offline
    fallback).
  - `SemanticEmbedder`: google-genai client (`embed_content`, Vertex,
    configurable model) with a **lazy** client (no network at construction)
    and a per-instance cache.
  - `build_embedder(settings)`: local → hashing; GCP → semantic.
- `vector_memory.py`: the GCP branch receives `embedder=build_embedder(settings)`;
  query embedding runs in `to_thread` (today it would block the event loop).
- Settings: `embedding_model` (default `text-embedding-005`).
- Local stays on TF-IDF (real, offline IR); hybrid BM25+vector is out of scope
  this cycle.

## 2. N-candidate tournament in the optimizer

- `MetaOptimizerEngine.run_tournament(candidate_count)`: propose N mutations →
  evaluate each against the calibration set → anti-gaming gate per candidate →
  **promote the best accepted one** (min MAE; tie-break higher QWK;
  deterministic). No accepted candidate → `winner=None`, no promotion.
- Diversity: the proposer protocol gains an optional third parameter
  `attempt: int = 0`; the engine passes it only if the proposer accepts it
  (signature inspection) → existing scripted proposers keep working.
  - `LlmProposer`: stepped temperature per attempt (0.2 + 0.15·attempt,
    capped 0.9) + a diversity hint in the payload.
  - `LocalHeuristicProposer`: rotates directives and adds an attempt marker →
    distinct, deterministic candidates.
- Deduplication of identical candidates (same instruction + few-shots) before
  evaluation.
- New `TournamentReport(candidates, winner)` schema; `run_iteration` stays
  backward compatible.
- Settings: `optimizer_candidates` (default 3, 1–8). `MetaOptimizerAgent.
  run_cycle` switches to tournaments and persists only the winner.

## 3. Evolving the auditor prompt

- **Honest metric mapping**: each expected criterion→competency mapping is
  worth 1.0; the evaluator produces "agreement" ∈ [0,1] per item →
  `CalibrationSample`/`compute_calibration_metrics`/anti-gaming are reused as
  is (MAE = 1 − mean agreement; constant-output still works; variance collapse
  self-disables because the ground truth is constant — the guard already
  exists).
- `agents/audit_calibration.py`: samples in
  `<local_data_dir>/calibration_audits/`; `LocalAuditEvaluator` (lexical
  agreement, same pattern as the local grading evaluator) and
  `AdkAuditEvaluator` (maps codes with Gemini and compares Jaccard vs
  expected) with `build_audit_evaluator(settings)`.
- `prompts/auditor_prompts.py`: `seed_auditor_prompt(registry)`; exported in
  `prompts/__init__`.
- `MetaOptimizerAgent`: `_seed` generalized with a per-`variant_id` seeder
  registry (grading and auditor); `build_meta_optimizer(scope="grading" |
  "auditor")` picks variant, evaluator and calibration directory per scope.
- OPTIMIZE stage: runs **both** optimizers (grading + auditor), each tolerant
  of missing calibration; `OptimizeOutputs.report` becomes
  `reports: list[OptimizerReport]`.

## Planned tests

1. `tests/core_memory/test_embeddings.py` — hashing determinism/dimensions;
   `build_embedder` local→hashing, GCP→semantic (no network: lazy client).
2. `tests/calibration/test_tournament.py` — best of N promoted; nothing
   accepted → no promotion; dedup; two-arg proposer compatibility; QWK
   tie-break.
3. `tests/calibration/test_audit_evolution.py` — audit samples load; full
   scope=auditor cycle with an enriched proposer → accepted and persisted; no
   improvement → rejected.
4. Full suite green.

## Impact

- Settings (+2), `.env.example` (+2), README (semantic L2 in GCP, tournament,
  auditor).
- `JobRunner`/`build_pipeline`/`build_sync_step`: singular `optimizer` →
  `optimizers` list; `dependencies` builds both; benchmarks unchanged in
  behavior.
