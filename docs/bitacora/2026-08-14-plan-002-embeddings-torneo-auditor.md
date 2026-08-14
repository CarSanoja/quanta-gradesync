# Bitácora — Plan 002: embeddings semánticos + torneo de candidatos + evolución del auditor

**Fecha:** 2026-08-14
**Dominio:** Planificación
**Resuelve:** Gaps 1–3 de la Auditoría 001
**Regla innegociable:** la suite completa sigue corriendo offline, sin credenciales.

## 1. Embeddings semánticos inyectables en L2

- Nuevo `core/memory/embeddings.py`: tipo `Embedder = Callable[[str], list[float]]`.
  - `HashingEmbedder`: el feature-hashing actual (fallback offline, determinista).
  - `SemanticEmbedder`: cliente google-genai (`embed_content`, Vertex, modelo configurable) con cliente **lazy** (sin red al construir) y caché por instancia.
  - `build_embedder(settings)`: local → hashing; GCP → semántico.
- `vector_memory.py`: la rama GCP recibe `embedder=build_embedder(settings)`; el embedding de la query se ejecuta en `to_thread` (hoy bloquearía el event loop).
- Settings: `embedding_model` (default `text-embedding-005`).
- Local queda en TF-IDF (IR real y offline); no se implementa hybrid BM25+vector en este ciclo.

## 2. Torneo de N candidatos en el optimizador

- `MetaOptimizerEngine.run_tournament(candidate_count)`: proponer N mutaciones → evaluar cada una contra el calibration set → gate anti-gaming por candidata → **promover la mejor aceptada** (mínimo MAE; tie-break mayor QWK; determinista). Sin aceptadas → `winner=None` y no hay promoción.
- Diversidad: el protocolo de proposer gana un tercer parámetro opcional `attempt: int = 0`; el motor lo pasa solo si el proposer lo acepta (inspección de firma) → los scripted proposers existentes siguen funcionando.
  - `LlmProposer`: temperatura escalonada por attempt (0.2 + 0.15·attempt, tope 0.9) + hint de diversidad en el payload.
  - `LocalHeuristicProposer`: rota directivas y añade marcador de intento → candidatos distintos y deterministas.
- Dedupe de candidatos idénticos (misma instrucción + few-shots) antes de evaluar.
- Nuevo schema `TournamentReport(candidates: list[OptimizerReport], winner: OptimizerReport | None)`; `run_iteration` se conserva retrocompatible.
- Settings: `optimizer_candidates` (default 3, 1–8). `MetaOptimizerAgent.run_cycle` pasa a torneo y persiste solo el ganador.

## 3. Evolución del prompt del auditor

- **Mapeo de métrica honesto**: cada mapeo esperado criterio→competencia vale 1.0; el evaluador produce "acuerdo" ∈ [0,1] por ítem → se reutilizan `CalibrationSample`/`compute_calibration_metrics`/anti-gaming tal cual (MAE = 1 − acuerdo medio; constant-output sigue operativo; variance-collapse se auto-desactiva porque el ground truth es constante — el guard ya existe).
- `agents/audit_calibration.py`: muestras en `<local_data_dir>/calibration_audits/`; `LocalAuditEvaluator` (acuerdo léxico, patrón del evaluador de grading local) y `AdkAuditEvaluator` (mapea códigos con Gemini y compara Jaccard vs esperado) con `build_audit_evaluator(settings)`.
- `prompts/auditor_prompts.py`: `seed_auditor_prompt(registry)`; export en `prompts/__init__`.
- `MetaOptimizerAgent`: `_seed` generalizado con registro de seeders por `variant_id` (grading y auditor); `build_meta_optimizer(scope="grading" | "auditor")` elige variante, evaluador y directorio de calibración por scope.
- Etapa OPTIMIZE: corre **ambos** optimizadores (grading + auditor), cada uno tolerante a calibración ausente; `OptimizeOutputs.report` pasa a `reports: list[OptimizerReport]`.

## Pruebas previstas

1. `tests/core_memory/test_embeddings.py` — determinismo/dim del hashing; `build_embedder` local→hashing, GCP→semántico (sin red: cliente lazy).
2. `tests/calibration/test_tournament.py` — mejor de N promovida; ninguna aceptada → sin promoción; dedupe; proposer 2-arg compatible; tie-break QWK.
3. `tests/calibration/test_audit_evolution.py` — muestras de auditoría cargan; ciclo completo scope=auditor con proposer enriquecido → aceptada y persistida; sin mejora → rechazada.
4. Suite completa `.venv/bin/pytest -q` en verde + reglas de archivo/comentarios.

## Impacto

- Settings (+2), `.env.example` (+2), README (L2 semántico en GCP, torneo, auditor).
- `JobRunner`/`build_pipeline`: `optimizer` singular → `optimizers` lista; `dependencies` construye ambos; benchmarks sin cambios de comportamiento (pasan `optimizers=None` implícito).
