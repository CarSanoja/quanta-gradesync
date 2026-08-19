# Dev log — Audit 002: is it an agentic system?

**Date:** 2026-08-15
**Domain:** Conceptual audit
**Question:** can it think, execute actions, check whether the goal was met,
and keep looping until it finishes in the best possible way?

## Conclusion

**Hybrid: a deterministic workflow with agentic islands.** The full agentic
loop exists today in the cold plane (self-improvement); in the hot plane,
execution is a fixed DAG with distributed verification gates but no goal
verifier and no rework.

## What exists

1. **Tool loop (micro-agency)**: ADK agents pick tools (fetch, vector
   search), observe and decide the next step.
2. **Repair loop**: an LLM output that violates the contract → retry with a
   corrective instruction.
3. **Self-improvement loop (fully agentic)**: state (prompt lineage in L3) →
   goal (MAE/QWK vs humans) → action (tournament of N mutations) →
   verification (improvement + anti-gaming) → persisted learning. The system
   directs its own improvement.
4. **Resilience loop**: checkpoints + Pub/Sub redelivery + resume — it
   iterates to completion through infrastructure.

## What was missing in the hot plane

1. **Goal verifier**: nobody evaluates after SYNC whether the job achieved
   its mission.
2. **Directed rework**: massive low confidence does not trigger a retry with
   another strategy.
3. **Autonomous convergence**: the optimizer runs one tournament per trigger;
   it does not iterate until converging.

## Why that is (partly) a design decision

In K-12 grading the hot path must be reproducible, auditable and
cost-predictable; agency is concentrated where it adds value (multimodal
judgment, self-improvement) and bounded by gates (schemas, anti-gaming,
confidence threshold). A free-roaming agent in the main pipeline would be a
legal liability, not a feature.

## Resolution

Plan 003 closes gaps 1–3 **without breaking the thesis**: bounded, traceable
verification and rework; convergence with a budget. The per-job planner stays
deferred: the fixed DAG is the correct auditable stance for this domain.
