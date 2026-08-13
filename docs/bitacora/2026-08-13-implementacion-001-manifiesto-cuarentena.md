# Bitácora — Implementación 001: manifiesto auto-inferido + cuarentena por confianza

**Fecha:** 2026-08-13
**Dominio:** Implementación
**Ejecuta:** Plan 001 (feedback 001)
**Verificación:** `.venv/bin/pytest -q` → **82 passed / 0 failed** (antes: 53; +29 tests nuevos). `compileall` limpio. Sin comentarios en código. Todos los archivos ≤ 200 líneas (máx. 194).

## Mejora 1 — Manifiesto auto-inferido (hecho)

- `core/orchestration/catalog_defaults.py` (nuevo): registro por periodo `catalog-defaults.json` en la raíz del bucket — bindings materia → grade_level + rúbrica + estándar.
- `core/orchestration/manifest_inference.py` (nuevo, 172 líneas): gramática `{año}_{materia}_{curso}_{evaluación}`, validación contra atributos del evento (mismatch → `CatalogError`), listado de entregas (1 archivo = 1 estudiante, stem = student_id), `LocalManifestInferer` + `FallbackJobCatalog`.
- `core/orchestration/manifest_inference_gcs.py` (nuevo): variante GCS (`list_blobs`).
- `catalog.py`: nueva `ManifestNotFound(CatalogError)` — solo el manifiesto *ausente* dispara inferencia; un manifiesto *inválido* falla ruidosamente (nunca se enmascara). `build_job_catalog` ahora devuelve el catálogo con fallback.
- QR/OCR de carátula: documentado como tercer modo sobre el mismo seam (no implementado en este ciclo).

## Mejora 2 — Cuarentena por confianza (hecho)

- `schemas/review.py` (nuevo): `ReviewItem` (review_id `{job_id}:{student_id}` idempotente, motivos, evidencias con página+cita, rutas de documento, record propuesto) + `ReviewStatus` (PENDING/APPROVED/DISMISSED).
- `core/review/gate.py`: `ConfidenceGate` — cuarentena si `min(confianza) < 0.85` o criterio sin evidencia citada; exactamente 0.85 pasa. Umbral configurable: `GRADESYNC_CONFIDENCE_THRESHOLD`.
- `core/review/store.py`: `ReviewStore` (Protocol) + `LocalReviewStore` (JSON por ítem) + `FirestoreReviewStore`.
- `core/review/service.py`: `ReviewService.approve` (escribe al SIS + actualiza L3 + marca APPROVED; doble approve → `ReviewStateError`), `dismiss`, `list_pending`.
- `core/orchestration/stages_sync.py` (nuevo; extraído de `stages_outcome.py` que quedó en 74 líneas): etapa SYNC particiona por gate — los de baja confianza van a la cola y **no** tocan SIS ni L3; `SISWriteResult.quarantined_count` (default 0, retrocompatible).
- `api/review.py` (nuevo): `GET /review/pending`, `POST /review/{id}/approve`, `POST /review/{id}/dismiss` con el mismo bearer token (401/403/404/409).
- `MemoryManager.persist_student_percentage`: merge incremental del `TermSnapshot` al aprobar.

## Mejora 3 — ROI y pitch (hecho)

- README: elevator pitch optimizado, matriz de flujos de entrada, 6 garantías fundamentales (incl. escalación por umbral de confianza), ROI (12 h/semana → ~10 min de excepciones; 14 días → <10 min), sección de convención de nombres con diagrama de bucket, y tabla de la API de revisión humana.
- `.env.example`: `GRADESYNC_CONFIDENCE_THRESHOLD=0.85`, `GRADESYNC_FIRESTORE_REVIEWS_COLLECTION=reviews`.

## Pruebas nuevas (29)

- `tests/orchestration/test_manifest_inference.py` (11): gramática válida/corta/vacía, inferencia end-to-end sin `batch.json`, manifiesto explícito gana, manifiesto inválido no se enmascara, mismatch de materia, defaults ausentes, materia sin binding, sin archivos graduables, `ManifestNotFound`.
- `tests/review/test_confidence_gate.py` (7): frontera exacta 0.85 pasa / 0.84 cuarentena, sin evidencia → cuarentena, mínimo entre criterios decide, umbral custom, valores inválidos.
- `tests/review/test_review_flow.py` (3): corrida completa del runner con un estudiante en 0.6 → COMPLETED, SIS sin ese record, ítem con página+cita+motivos+ruta, L3 intacta; approve → SIS + L3 + idempotencia (segundo approve falla); dismiss cierra sin escribir.
- `tests/api/test_review_endpoints.py` (8): auth 401/403, pending vacío/lleno, approve 200/404/409, dismiss sin escritura.

## Correcciones durante verificación

1. `parse_lot_code`: prefijos solo-espacios ahora se tratan como vacíos (antes caían al error de convención).
2. `document_paths` del `ReviewItem` usa el `gcs_uri` estable en vez del `local_path` efímero de la instancia.
3. Tests de benchmark: el evaluador scriptado ahora cita evidencia con confianza 0.95 (un agente que pasa el gate), y el runner recibe `review_store` explícito.
4. División por responsabilidad: `catalog_defaults.py`, `stages_sync.py`, `tests/review/flow_stack.py`, `tests/orchestration/inference_fixtures.py` — nada supera 200 líneas.
