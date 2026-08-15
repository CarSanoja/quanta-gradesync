# Bitácora — Implementación 003: cierre agéntico (verificación de meta + convergencia)

**Fecha:** 2026-08-15
**Dominio:** Implementación
**Ejecuta:** Plan 003 (gaps 1–3 de la Auditoría 002)
**Verificación:** `.venv/bin/pytest -q` → **107 passed / 0 failed** (antes: 99; +8 tests). `compileall` limpio. Sin comentarios. Archivos ≤ 200 líneas. Suite 100% offline.

## Verificador de meta con re-trabajo acotado (hecho)

- Nueva etapa **VERIFY** entre SYNC y OPTIMIZE (`JobStage.VERIFIED`, reanudable por checkpoint como toda etapa).
- `core/orchestration/goal_checks.py`: 5 checks deterministas — `submissions_graded`, `audits_complete`, `risk_complete`, `sis_auto_synced`, `quarantine_accounted` (los ítems PENDING del job deben igualar los registros en cuarentena).
- `core/orchestration/verifier.py`: el loop agéntico acotado — **mientras** haya cuarentenas sin reintentar, iteración ≤ `verify_max_iterations` y la iteración anterior recuperó algo: re-grade con **segunda opinión** (`agents/rework_evaluator.py`: GCP → Gemini Flash en vez de Pro; local → `None`, verificación sin re-trabajo, documentado) → gate de confianza → si pasa, **actualiza el `ReviewItem`** con el nuevo record, razones y `rework_notes` — **sigue PENDING**: la aprobación de 1 clic sigue siendo del docente (gobernanza del feedback 001 innegociable). Sin progresos → el loop corta.
- `VerificationReport` distingue explícitamente `pending_human_approval` (recuperados esperando clic) de `unresolved_submission_ids` (siguen requiriendo ojos humanos). `passed = checks ∧ unresolved = ∅`. Persistido en el checkpoint del job.

## Convergencia del optimizador (hecho)

- `MetaOptimizerAgent.run_until_convergence()`: torneos en loop — para cuando un ciclo no acepta nada (nada que aprender), la mejora marginal < ε (convergió) o se agota `max_cycles` (presupuesto).
- La etapa OPTIMIZE usa el loop; `OptimizeOutputs.reports` acumula los ganadores de todos los ciclos.
- Settings: `GRADESYNC_OPTIMIZER_MAX_CYCLES=3`, `GRADESYNC_OPTIMIZER_CONVERGENCE_MIN_IMPROVEMENT=0.01`, `GRADESYNC_VERIFY_MAX_ITERATIONS=2`.

## Planner por job — diferido (decisión documentada)

El DAG fijo sigue siendo la postura auditable correcta para corrección K-12; registrado en la Auditoría 002 como decisión, no deuda.

## Pruebas nuevas (8)

- `tests/orchestration/test_verifier.py` (5) + `verifier_fixtures.py`: job limpio pasa los 5 checks; re-trabajo recupera cuarentena **pero el ítem sigue PENDING** con `rework_notes` y record al 90% (aprobación humana intacta); re-trabajo que no recupera → unresolved y `passed=False`; sin evaluador de re-trabajo → cuarentena unresolved (comportamiento local); presupuesto de iteraciones acota el loop (1 iteración deja unresolved, 2 converge).
- `tests/calibration/test_convergence.py` (3): para por mejora marginal < ε (2 ganadores, 3 versiones); para al no aceptar nada (0 ganadores, sin promoción); respeta `max_cycles=2` con mejoras constantes.

## Hallazgos durante verificación

1. Test de convergencia detectó interacción real: con `optimizer_candidates=3` el torneo consume varias mutaciones por ciclo — el test ahora aísla la convergencia con 1 candidata por ciclo (documentado implícitamente en el propio test).
2. Split por responsabilidad para mantener ≤200: `goal_checks.py` fuera de `verifier.py`, `verifier_fixtures.py` fuera del test.
