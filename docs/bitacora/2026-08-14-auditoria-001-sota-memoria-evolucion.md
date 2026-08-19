# Dev log — Audit 001: SOTA level of memory and self-improvement

**Date:** 2026-08-14
**Domain:** Technical audit
**Conclusion:** complete SOTA-pattern architecture; real algorithms; three
deliberate simplifications → Plan 002.

## Memory

### L1 — Session State (`core/memory/session_memory.py`) — SOTA ✅
Typed per-job state (`stage_results`/`stage_statuses`), re-validated with
`TypeAdapter` on checkpoint restore — crash resume is type-safe. Stricter
than the untyped-dict pattern.

### L2 — Vector Search (`core/memory/vector_memory.py`) — SOTA with a caveat ⚠️
- Local: real TF-IDF (smoothed IDF, sparse cosine, deterministic tie-break,
  zero-score cutoff).
- GCP: Firestore `find_nearest` with COSINE — genuinely managed vector
  search.
- **Caveat:** the default embedder is SHA-256 *feature hashing* → lexical,
  not semantic. Injectable, but without real embeddings synonyms do not
  cluster.

### L3 — Managed Cloud Memory (`persistent_memory.py`, `manager.py`) — SOTA ✅
Memory as curated knowledge (schema'd aggregates), not chat logs. Local JSON
and Firestore backends. Confirmed-outcome writes only.

## Self-evolution

Complete loop in production (OPTIMIZE stage): calibration (MAE/QWK/bias) →
proposer (structured LLM / local heuristic) → re-evaluation on the same ground
truth → `AntiGamingValidator` (constant output, variance collapse with a
`truth_std × 0.75` floor, ground-truth contact) → versioned promotion with
rollback and L3 persistence.

The anti-gaming gate **exceeds** the standard codelab pattern.

## Gaps (ranked by impact/cost)

1. **Semantic embeddings in L2** — wire Vertex text embeddings into the
   injectable embedder. Low cost, high impact on curriculum retrieval.
2. **Single-candidate evolution** — today incumbent vs 1 challenger; full
   SOTA = a tournament of N mutations promoting the best.
3. **Only the grading prompt evolves** — `auditor-v1` is seeded but the engine
   does not evolve it.
4. No shadow rollout of accepted variants (future).
5. No dedicated nightly scheduler (future).
6. No per-criterion production drift monitoring (future).
