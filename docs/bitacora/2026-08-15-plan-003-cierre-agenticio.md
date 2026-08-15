# Bitácora — Plan 003: cierre agéntico (verificación de meta + convergencia)

**Fecha:** 2026-08-15
**Dominio:** Planificación
**Resuelve:** Gaps 1–3 de la Auditoría 002
**Innegociable:** la suite sigue offline en verde y la gobernanza humana de la cuarentena NO se bypassa.

## 1. Etapa VERIFY con re-trabajo acotado (plano caliente)

Nueva etapa entre SYNC y OPTIMIZE (`JobStage.VERIFIED`):

**GoalChecks deterministas** (todos deben pasar):
- `submissions_graded`: cada entrega del lote tiene `GradingResult`.
- `audits_complete`: cada resultado calificado tiene auditoría curricular.
- `risk_complete`: cada estudiante del lote tiene `RiskAssessment`.
- `sis_auto_synced`: la escritura al SIS no dejó fallos.
- `quarantine_accounted`: cada estudiante en cuarentena tiene ítem PENDING en la cola.

**Loop de re-trabajo acotado** (agencia real con presupuesto):
- `while` haya cuarentenas sin reintentar Y `iteración < verify_max_iterations`:
  1. **Actuar**: re-grade las entregas en cuarentena con un evaluador de **segunda opinión** (GCP: Gemini Flash en vez de Pro; local: no hay segunda opinión real → verificación sin re-trabajo, documentado).
  2. **Verificar meta**: el resultado re-calificado pasa el `ConfidenceGate`.
  3. **Decidir**: si pasa → **actualiza el `ReviewItem`** con el nuevo record propuesto, evidencia y `rework_notes` — **sigue PENDING**: la aprobación de 1 clic sigue siendo del docente (la gobernanza del feedback 001 es innegociable). Si no pasa → queda como `unresolved`.
  4. Sin recuperaciones en una iteración → el loop corta (no insiste en lo que no da más de sí).
- Salida: `VerificationReport` con checks, intentos, `pending_human_approval` (recuperados esperando clic) y `unresolved_submission_ids` (siguen requiriendo ojos humanos). `passed = checks ∧ unresolved = ∅`.

## 2. Convergencia del optimizador (plano frío)

`MetaOptimizerAgent.run_until_convergence(min_improvement, max_cycles)`:
- Corre torneos en loop: **para** cuando un ciclo no acepta nada (nada que aprender) **o** la mejora marginal < ε (convergió) **o** al agotar `max_cycles` (presupuesto).
- La etapa OPTIMIZE usa este loop; `OptimizeOutputs.reports` acumula los ganadores por ciclo.
- Settings: `optimizer_max_cycles` (default 3, 1–10), `optimizer_convergence_min_improvement` (default 0.01).

## 3. Planner por job — diferido

El DAG fijo es la postura auditable correcta para corrección K-12 (reproducibilidad y recibo por decisión). Diferido conscientemente; documentado aquí como decisión, no como deuda.

## Pruebas previstas

1. `tests/orchestration/test_verifier.py` — checks en verde sin cuarentena; recuperación vía re-trabajo (ítem actualizado, sigue PENDING, aprobación humana intacta); re-trabajo que no recupera → unresolved y `passed=False`; límite de iteraciones respetado; loop corta sin progresos.
2. `tests/calibration/test_convergence.py` — para por ε; para al no aceptar; respeta max_cycles.
3. Suite completa `.venv/bin/pytest -q` en verde.

## Impacto

- `schemas/verification.py` (nuevo), `ReviewItem.rework_notes` (campo con default, retrocompatible), `JobStage.VERIFIED`, `core/orchestration/verifier.py` (nuevo), `agents/rework_evaluator.py` (nuevo), wiring en `graph/runner/dependencies`, settings (+3), `.env.example` (+3), README.
