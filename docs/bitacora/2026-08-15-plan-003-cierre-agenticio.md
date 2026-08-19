# Dev log — Plan 003: agentic closure (goal verification + convergence)

**Date:** 2026-08-15
**Domain:** Planning
**Solves:** Gaps 1–3 of Audit 002
**Non-negotiable:** the suite stays offline-green and the human governance of
quarantine is NOT bypassed.

## 1. VERIFY stage with bounded rework (hot plane)

New stage between SYNC and OPTIMIZE (`JobStage.VERIFIED`):

**Deterministic goal checks** (all must pass):
- `submissions_graded`: every submission in the batch has a `GradingResult`.
- `audits_complete`: every graded result has a curriculum audit.
- `risk_complete`: every student in the batch has a `RiskAssessment`.
- `sis_auto_synced`: the SIS write left no failures.
- `quarantine_accounted`: every quarantined student has a PENDING item in the
  review queue.

**Bounded rework loop** (real agency with a budget):
- `while` there are unattempted quarantines AND
  `iteration < verify_max_iterations`:
  1. **Act**: re-grade the quarantined submissions with a **second-opinion**
     evaluator (GCP: Gemini Flash instead of Pro; local: no real second
     opinion → verification without rework, documented).
  2. **Verify the goal**: the re-graded result passes the `ConfidenceGate`.
  3. **Decide**: if it passes → **update the `ReviewItem`** with the new
     proposed record, evidence and `rework_notes` — **it stays PENDING**:
     the one-click approval remains the teacher's (the feedback-001
     governance is non-negotiable). If it fails → it remains `unresolved`.
  4. No recoveries in an iteration → the loop stops.
- Output: a `VerificationReport` with checks, attempts,
  `pending_human_approval` (recovered, awaiting a click) and
  `unresolved_submission_ids` (still needing human eyes).
  `passed = checks ∧ unresolved = ∅`.

## 2. Optimizer convergence (cold plane)

`MetaOptimizerAgent.run_until_convergence(min_improvement, max_cycles)`:
- Loops tournaments: **stops** when a cycle accepts nothing (nothing to
  learn) **or** the marginal improvement drops below ε (converged) **or** the
  `max_cycles` budget runs out.
- The OPTIMIZE stage uses this loop; `OptimizeOutputs.reports` accumulates
  the per-cycle winners.
- Settings: `optimizer_max_cycles` (default 3, 1–10),
  `optimizer_convergence_min_improvement` (default 0.01).

## 3. Per-job planner — deferred

The fixed DAG is the correct auditable stance for K-12 grading
(reproducibility and a receipt per decision). Deliberately deferred;
recorded here as a decision, not debt.

## Planned tests

1. `tests/orchestration/test_verifier.py` — green checks without quarantine;
   recovery via rework (item updated, still PENDING, human approval intact);
   rework that does not recover → unresolved and `passed=False`; iteration
   budget respected; loop stops without progress.
2. `tests/calibration/test_convergence.py` — stops on ε; stops when nothing
   is accepted; respects max_cycles.
3. Full suite green.

## Impact

- `schemas/verification.py` (new), `ReviewItem.rework_notes` (defaulted,
  backward-compatible field), `JobStage.VERIFIED`,
  `core/orchestration/verifier.py` (new), `agents/rework_evaluator.py` (new),
  wiring in `graph/runner/dependencies`, settings (+3), `.env.example` (+3),
  README.
