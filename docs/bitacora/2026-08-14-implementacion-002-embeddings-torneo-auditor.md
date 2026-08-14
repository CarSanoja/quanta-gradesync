# Bitácora — Implementación 002: embeddings semánticos + torneo + evolución del auditor

**Fecha:** 2026-08-14
**Dominio:** Implementación
**Ejecuta:** Plan 002 (gaps 1–3 de la Auditoría 001)
**Verificación:** `.venv/bin/pytest -q` → **99 passed / 0 failed** (antes: 82; +17 tests). `compileall` limpio. Sin comentarios. Todos los archivos ≤ 200 líneas (máx. 194). Suite 100% offline.

## Gap 1 — Embeddings semánticos (hecho)

- `core/memory/embeddings.py` (nuevo, 86 líneas): tipo `Embedder`; `HashingEmbedder` (fallback determinista); `SemanticEmbedder` con cliente google-genai **lazy** (cero red al construir) y caché por instancia; `build_embedder(settings)` selecciona por modo.
- `vector_memory.py`: la rama GCP inyecta `build_embedder(settings)` — L2 ahora recupera con embeddings reales de Vertex (`GRADESYNC_EMBEDDING_MODEL`, default `text-embedding-005`); el embedding de query se ejecuta en `to_thread` (antes bloqueaba el event loop). Local sigue con TF-IDF real.
- Verificado sin red: test con cliente falso confirma caché (2 embeds → 1 llamada API).

## Gap 2 — Torneo de N candidatos (hecho)

- `optimizer_engine.py` (192 líneas): `run_tournament(candidate_count)` propone N mutaciones, evalúa cada una contra el mismo ground truth, gate anti-gaming por candidata, **promueve solo la mejor aceptada** (min MAE, tie-break mayor QWK). Dedupe por (instrucción, few-shots) antes de evaluar. Sin aceptadas → `winner=None`, cero promoción.
- `TournamentReport` (schema nuevo) con invariante: el ganador debe ser una de las candidatas y estar aceptada.
- Diversidad sin romper compatibilidad: `call_proposer` pasa `attempt` solo si el proposer lo acepta (inspección de firma) — los scripted proposers existentes siguen funcionando. `LlmProposer` escala temperatura por intento (0.2→0.9) + directiva de diversidad; `LocalHeuristicProposer` rota directivas por intento.
- `GRADESYNC_OPTIMIZER_CANDIDATES=3` (1–8). `run_iteration` se conserva retrocompatible (53 tests previos intactos).

## Gap 3 — Evolución del auditor (hecho)

- Mapeo de métrica honesto: cada mapeo esperado criterio→competencia vale 1.0; el evaluador produce acuerdo ∈ [0,1] por ítem; se reutilizan íntegros `CalibrationSet`, `compute_calibration_metrics` y el `AntiGamingValidator`.
- `agents/audit_samples.py` (nuevo): dir `calibration_audits/`, loader y constructor de muestras.
- `agents/audit_calibration.py` (nuevo, 194): `LocalAuditEvaluator` — acuerdo por ítem consciente de si el prompt **cita el mapeo específico** (0.5·cita + 0.5·cobertura léxica, piso 0.25); `AdkAuditEvaluator` (GCP) mapea códigos con Gemini Flash y compara Jaccard.
- `MetaOptimizerAgent` generalizado: seeders por `variant_id` (grading + auditor); `agents/optimizer_factory.py` (nuevo): `build_meta_optimizer(scope="grading"|"auditor")` y `build_optimizer_fleet` — la etapa OPTIMIZE ahora corre **ambos** optimizadores y `OptimizeOutputs` recopila `reports: list`.

## Corrección de diseño durante la implementación

El `LocalAuditEvaluator` original puntuaba todos los ítems de una muestra con la misma cobertura → varianza intra-muestra siempre cero → el anti-gaming habría rechazado **toda** candidata (falso positivo sistemático). Rediseñado el evaluador para puntuar por ítem según cita explícita del mapeo: las candidatas que citan mapeos concretos superan el gate; las planas, no. El test `test_local_audit_evaluator_rewards_cited_mappings` clava el comportamiento.

## Pruebas nuevas (17)

- `tests/core_memory/test_embeddings.py` (6): determinismo/normalización del hashing, vector cero sin tokens, dimensiones inválidas, selección local/GCP, cliente lazy sin red, caché sin llamadas repetidas.
- `tests/calibration/test_tournament.py` (5) + `test_tournament_selection.py` (3): mejor de N promovida; ninguna aceptada → sin promoción; dedupe (3 intentos → 1 evaluación); `attempt` solo si el proposer lo soporta; tie-break por QWK ignorando rechazadas; `winner=None` sin aceptadas; conteo inválido → error.
- `tests/calibration/test_audit_evolution.py` (5): el evaluador local premia citas de mapeo; scope auditor acepta y persiste la mejora (jsonl con `auditor-v1`); candidata plana rechazada sin persistir; scope desconocido → error; carga de muestras de auditoría.
