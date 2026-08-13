# Bitácora — Plan 001: manifiesto auto-inferido + cuarentena por confianza

**Fecha:** 2026-08-13
**Dominio:** Planificación
**Resuelve:** Feedback 001 (puntos 1 y 2; punto 3 es documentación)
**Estado:** Ejecutado — ver entrada de implementación 001

## Mejora 1 — Manifiesto auto-inferido por convención

**Problema:** hoy `LocalJobCatalog`/`GcsJobCatalog` exigen `batch.json` por lote (`catalog.py:15`). Llenarlo por evaluación rompe la promesa "sube archivos y desaparece".

**Diseño:**
- Nueva excepción `ManifestNotFound(CatalogError)` para distinguir "no hay manifiesto" de "el manifiesto existe pero es inválido" (este último **nunca** se reemplaza silenciosamente: falla ruidoso).
- `FallbackJobCatalog`: intenta el manifiesto explícito; si no existe, infiere.
- **Gramática de convención** para el último segmento del prefijo: `{año}_{materia}_{curso}_{evaluación}` (ej. `2026_Matematicas_10A_Parcial1`). Sujeto y curso deben coincidir con el evento Pub/Sub (fuente de verdad); discrepancia o token ambiguo → `CatalogError` con el motivo exacto. El sistema nunca adivina.
- **Listado de entregas**: cada archivo con MIME permitido bajo el prefijo es una entrega; `student_id`/`submission_id` = stem del archivo (el docente escanea `juanp001.jpg`). Local: walk del staging; GCP: `list_blobs`.
- **Registro de rúbricas** `catalog-defaults.json` en la raíz del bucket (una vez por periodo, lo define coordinación): mapea materia → `grade_level` + `Rubric` + `CurriculumStandard`. Sin registro para la materia → `CatalogError`.
- Carátula QR/OCR: queda como extensión futura del mismo seam (otro `ManifestNotFound` resolver); documentado, no implementado en este ciclo.

**Archivos:** nuevo `core/orchestration/manifest_inference.py`; edición de `catalog.py` (subclase de excepción) y `build_job_catalog` (envuelve en fallback).

## Mejora 2 — Cuarentena por confianza (gate 0.85)

**Problema:** escribir el 100% de las notas al SIS sin validación humana es inaceptable para K-12 formal.

**Diseño (nuevo dominio `core/review/`):**
- `schemas/review.py`: `ReviewStatus` (PENDING/APPROVED/DISMISSED), `ReviewItem` (review_id determinista `{job_id}:{student_id}` → re-enqueue idempotente; motivos; `EvidenceSpan`s con página+cita = el "recorte pre-resaltado"; rutas de documento; `SISGradeRecord` propuesto; timestamps).
- `core/review/gate.py`: `ConfidenceGate(threshold)` → cuarentena si `min(confianza de criterios) < threshold` **o** algún criterio sin evidencia. Umbral por settings `GRADESYNC_CONFIDENCE_THRESHOLD` (default 0.85). Exactamente 0.85 pasa (regla `>=`).
- `core/review/store.py`: `ReviewStore` Protocol + `LocalReviewStore` (JSON por ítem) + `FirestoreReviewStore`; `build_review_store(settings)`.
- `core/review/service.py`: `ReviewService.approve(review_id)` → escribe ese record al SIS + actualiza L3 del estudiante + marca APPROVED (segundo approve → error de estado → 409). `dismiss` cierra sin escribir. `list_pending` para el endpoint.
- **Etapa SYNC reescrita** (`stages_outcome.build_sync_step`): particiona los records por estudiante; los de baja confianza van a la cola de revisión y **no** se escriben al SIS ni contaminan L3 (los perfiles episódicos solo registran outcomes confirmados); los demás se escriben igual que hoy. `SISWriteResult` gana `quarantined_count` (default 0, compatible hacia atrás).
- **API**: `GET /review/pending`, `POST /review/{id}/approve`, `POST /review/{id}/dismiss` con el mismo bearer token — la aprobación de 1 clic.
- RISK sigue evaluando todas las entregas (la alerta temprana no espera aprobación).

## Mejora 3 — ROI y pitch (documental)

- README: elevator pitch optimizado del feedback, matriz de flujos de entrada con metadatos auto-inferidos, garantías fundamentales (6, incl. escalación por umbral de confianza), ROI (12 h/semana → ~10 min de excepciones; time-to-feedback 14 días → <10 min).
- `.env.example`: `GRADESYNC_CONFIDENCE_THRESHOLD`, `GRADESYNC_FIRESTORE_REVIEWS_COLLECTION`.

## Plan de pruebas

1. `tests/orchestration/test_manifest_inference.py` — gramática (happy, 3 tokens → error, mismatch con evento → error), inferencia end-to-end sin `batch.json` con registro de rúbricas, manifiesto explícito sigue ganando, manifiesto inválido no se reemplaza.
2. `tests/review/test_confidence_gate.py` — frontera 0.85 pasa / 0.84 cuarentena; sin evidencia → cuarentena; mínimo entre criterios.
3. `tests/review/test_review_flow.py` — corrida completa del runner con un estudiante en 0.6: job COMPLETED, SIS sin ese record, ítem PENDING con página+evidencia+motivos; approve → SIS lo recibe + L3 actualizado; doble approve → error; dismiss.
4. `tests/api/test_review_endpoints.py` — auth 401/403, pending vacío→lleno, approve 200/404/409.
5. Suite completa `.venv/bin/pytest -q` en verde (benchmarks ajustados: el evaluador scriptado ahora cita evidencia, como un buen agente).

## Impacto en código existente

- `JobRunner`/`build_pipeline`/`build_sync_step` ganan `review_store` y `confidence_threshold` (constructores explícitos: `bench_fixtures.py` y `dependencies.py` actualizados).
- `MemoryManager` gana `persist_student_percentage` público (aprobación unitaria).
- Sin cambios de comportamiento en RISK/AUDIT/OPTIMIZE ni en idempotencia.
