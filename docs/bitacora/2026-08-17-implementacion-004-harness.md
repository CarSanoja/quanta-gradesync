# Bitácora — Implementación 004: Agent Harness (gobernanza, contención, control)

**Fecha:** 2026-08-17
**Dominio:** Implementación
**Ejecuta:** Plan 004
**Verificación:** `.venv/bin/pytest -q` → **139 passed / 0 failed** (antes: 107; +32 tests). `compileall` limpio. Sin comentarios. Archivos ≤ 200 líneas. Suite 100% offline.

## Nuevo dominio `core/harness/` (generalizable, sin código de dominio dentro)

- `actions.py`: `ToolAction`, `ActionRisk` (pasiva / mutación interna / mutación externa), `PermissionDecision`, `PermissionVerdict`.
- `permission_gate.py`: pipeline de reglas con prioridad **DENY > QUARANTINE > ALLOW**; reglas genéricas `scope_rule` (fuera de scope → DENY en memoria, antes de red) y `confidence_rule` (mutación externa bajo umbral → QUARANTINE); fábrica `manifest_scope_gate`.
- `budgets.py`: `ItemBudget` (máx. 4 invocaciones por examen; `schema_repair_attempts=2` formalizado — ya existía en `agents/base.py:120`, ahora es presupuesto explícito del harness) + `guard_item`.
- `faithfulness.py`: verificador exact-match de `EvidenceSpan.quote` contra transcripción de página (normalización de espacios/mayúsculas); cita alucinada → confianza 0.0 → la cuarentena existente la captura. `SidecarTextProvider` + sidecars `.txt` junto al escaneo.
- `breakers.py`: `BatchAnomalyBreaker` — ratio de cuarentena > 15% → `BreakerTripped`.
- `provenance.py`: sha256 del prompt versionado (canónico JSON) y de cada evidencia.
- `eval_harness/objective_gate.py`: gate compuesto `QWK ≥ 0.85 ∧ MAE ≤ 0.4 ∧ |Bias| < 0.1` con umbrales por scope (auditor: sin QWK — verdad constante lo vuelve mal definido — y bias ≤ 0.3, documentado).
- `eval_harness/eval_runner.py`: corrida contra el golden dataset → `GoldenSummary`.

## Integraciones

1. **SYNC** (`stages_sync.py` + `sync_governance.py` + `sync_io.py`): cada registro pasa el permission gate antes del conector; breaker suspende el auto-sync del lote completo (todos a revisión con motivo); cada registro (auto y cuarentenado) queda estampado con `Provenance`.
2. **GRADE** (`stages_assessment.py`): blast-radius — un examen que explota o agota presupuesto se aísla, el lote continúa; faithfulness con sidecars activo por defecto.
3. **Optimizador**: el ganador del torneo debe superar además el objective gate (rechazo con `objective gate: …` en reasons); ratio anti-variance por defecto 0.25→**0.20** configurable; todo por settings.
4. **RISK**: salta estudiantes sin resultados (hueco del blast-radius) — el verificador de meta lo reporta.
5. **CI**: `tests/harness/golden_baseline.json` + test anti-regresión (el evaluador local léxico es un proxy — QWK −0.30 sobre los goldens — por eso CI fija *no-regresión contra baseline*; los umbrales absolutos aplican en runtime contra el evaluador real, documentado en el propio baseline).

## Decisiones y hallazgos

- **Conflicto de escalas resuelto**: los umbrales absolutos del feedback (MAE 0.4, bias 0.1) están pensados para notas 0–4; para el scope auditor (acuerdo 0–1) el bias 0.1 bloquearía toda mejora legítima → umbrales por scope, documentados en el plan y el código.
- **Bug real cazado por el test de procedencia**: `partition_by_gate` solo recolectaba evidencia de los cuarentenados → los registros auto-sincronizados (justo los que van al SIS) habrían llegado con ledger vacío. Corregido.
- Tests de convergencia actualizados: sus métricas sintéticas ahora deben superar el objective gate (política nueva); se detectó además un error aritmético en una aserción preexistente (mejora 0.5, no 0.25).
- División por responsabilidad para ≤200 líneas: `outcome_writers.py`, `sync_governance.py`, `sync_io.py`, `engine_support.py`.

## Pruebas nuevas (32)

- `tests/harness/test_permission_and_breakers.py` (10): ALLOW/DENY/QUARANTINE, prioridad, frontera 0.85, acciones pasivas ignoradas, breaker trip/pasa/inválidos.
- `tests/harness/test_budgets_faithfulness_provenance.py` (12): presupuesto y aislamiento, normalización de citas, alucinación → confianza 0, sidecars, shas deterministas y sensibles a versión/instrucción.
- `tests/harness/test_objective_gate_and_regression.py` (8): matriz del gate, umbrales por scope, motor rechaza ganador que no supera el gate y promueve cuando lo supera, gate anti-regresión contra baseline.
- `tests/harness/test_harness_pipeline.py` (4, e2e): blast-radius (job COMPLETED, verificador reporta 2/3), breaker de lote (cero escrituras SIS, 3 en revisión, motivo en el ítem previamente auto), ledger de procedencia en el jsonl (sha-256 de prompt y evidencias), cita alucinada → cuarentena.

## Documentación actualizada (política vigente)

- `docs/product/how-it-works.md`: nueva sección 9 "The agent harness" + renumeración + mapa de archivos.
- `docs/product/product-overview.md`: garantías 5–8 (gate compuesto, blast-radius, ledger de procedencia, breaker de lote) + roadmap.
- README: sección "Agent Harness" + 9 variables nuevas en `.env.example`.
