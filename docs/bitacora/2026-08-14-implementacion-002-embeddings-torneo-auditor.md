# Dev log — Implementation 002: semantic embeddings + tournament + auditor evolution

**Date:** 2026-08-14
**Domain:** Implementation
**Executes:** Plan 002 (gaps 1–3 of Audit 001)
**Verification:** `.venv/bin/pytest -q` → **99 passed / 0 failed** (was 82;
+17 tests). Clean `compileall`. No comments. Every file ≤ 200 lines (max 194).
Suite 100% offline.

## Gap 1 — Semantic embeddings (done)

- `core/memory/embeddings.py` (new, 86 lines): `Embedder` type;
  `HashingEmbedder` (deterministic fallback); `SemanticEmbedder` with a
  **lazy** google-genai client (zero network at construction) and per-instance
  cache; `build_embedder(settings)` selects by mode.
- `vector_memory.py`: the GCP branch injects `build_embedder(settings)` — L2
  now retrieves with real Vertex embeddings
  (`GRADESYNC_EMBEDDING_MODEL`, default `text-embedding-005`); query embedding
  runs in `to_thread` (previously it blocked the event loop). Local keeps the
  real TF-IDF index.
- Verified offline: a fake-client test confirms caching (2 embeddings → 1 API
  call).

## Gap 2 — N-candidate tournament (done)

- `optimizer_engine.py`: `run_tournament(candidate_count)` proposes N
  mutations, evaluates each against the same ground truth, applies the
  anti-gaming gate per candidate and **promotes only the best accepted one**
  (min MAE, tie-break higher QWK). Dedup by (instruction, few-shots) before
  evaluation. Nothing accepted → `winner=None`, zero promotion.
- `TournamentReport` (new schema) with the invariant: the winner must be one
  of the candidates and must be accepted.
- Diversity without breaking compatibility: `call_proposer` passes `attempt`
  only if the proposer accepts it (signature inspection) — existing scripted
  proposers keep working. `LlmProposer` steps temperature per attempt
  (0.2→0.9) plus a diversity directive; `LocalHeuristicProposer` rotates
  directives per attempt.
- `GRADESYNC_OPTIMIZER_CANDIDATES=3` (1–8). `run_iteration` preserved for
  backward compatibility (the 53 pre-existing tests stayed intact).

## Gap 3 — Auditor evolution (done)

- Honest metric mapping: each expected criterion→competency mapping is worth
  1.0; the evaluator produces per-item agreement; `CalibrationSet`,
  `compute_calibration_metrics` and `AntiGamingValidator` are reused whole.
- `agents/audit_samples.py` (new): `calibration_audits/` directory, loader
  and sample builder.
- `agents/audit_calibration.py` (new, 194 lines): `LocalAuditEvaluator` —
  per-item agreement aware of whether the prompt **cites the specific
  mapping** (0.5·citation + 0.5·lexical coverage, 0.25 floor);
  `AdkAuditEvaluator` (GCP) maps codes with Gemini Flash and scores Jaccard.
- `MetaOptimizerAgent` generalized: seeders per `variant_id` (grading +
  auditor); `agents/optimizer_factory.py` (new):
  `build_meta_optimizer(scope="grading"|"auditor")` and
  `build_optimizer_fleet` — the OPTIMIZE stage now runs **both** optimizers
  and `OptimizeOutputs` collects `reports: list`.

## Design fix during implementation

The original `LocalAuditEvaluator` scored every item of a sample with the
same coverage → within-sample variance always zero → anti-gaming would have
rejected **every** auditor candidate (a systematic false positive). The
evaluator was redesigned to score per item by explicit mapping citation:
candidates that cite concrete mappings pass the gate; flat ones do not.
`test_local_audit_evaluator_rewards_cited_mappings` pins the behavior.

## New tests (17)

- `tests/core_memory/test_embeddings.py` (6): hashing determinism/
  normalization, zero vector without tokens, invalid dimensions, local/GCP
  selection, lazy client without network, cache without repeated calls.
- `tests/calibration/test_tournament.py` (5) + `test_tournament_selection.py`
  (3): best of N promoted; none accepted → no promotion; dedup (3 attempts →
  1 evaluation); `attempt` only when supported; QWK tie-break ignoring
  rejected; `winner=None` without acceptance; invalid count → error.
- `tests/calibration/test_audit_evolution.py` (5): the local evaluator
  rewards cited mappings; auditor scope accepts and persists the improvement
  (jsonl with `auditor-v1`); flat candidate rejected without persisting;
  unknown scope → error; audit sample loading.
