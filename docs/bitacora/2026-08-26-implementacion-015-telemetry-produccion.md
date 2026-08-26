# Dev log — Implementación 015: telemetría de tres capas verificada en producción

**Fecha:** 2026-08-26 · **Rama:** main · **Revisión Cloud Run:** `autocurricula-gradesync-00019-x4w` (imagen `:b70c099`)

Cierra el "What is still unproven" de la [implementación 014](2026-08-25-implementacion-014-live-telemetry.md): la ruta cloud quedó ejecutada y medida, no solo construida.

## Dos defectos reales encontrados al verificar contra GCP

1. **`telemetry.googleapis.com` rechazaba todos los batches OTLP con 400.** El endpoint exige el atributo de recurso `gcp.project_id` y `install_telemetry` no pasaba ningún resource a `maybe_set_otel_providers`. Fix en `50087fd`: `get_gcp_resource(settings.gcp_project_id)` de ADK + dependencia `opentelemetry-resourcedetector-gcp` para que Cloud Run mapee al monitored resource correcto. Verificado contra el endpoint vivo: `SpanExportResult.SUCCESS`.
2. **Traces incompletos desde Cloud Run (13 spans de ~190).** El `BatchSpanProcessor` exporta en un hilo de fondo y Cloud Run estrangula la CPU al cerrar el request. Fix en `b70c099`: `flush_telemetry()` (force_flush del provider) junto al flush del live sink, dentro del request.

## Evidencia de producción (job real, disparado por GCS server-side)

- Job `demo-d06ff395-2026-matematicas-10a-parcial1`: **completed en ~84 s**, 14 synced / 2 quarantined (scan ilegible + inyección manuscrita), 144 eventos live, **34 llamadas LLM reales** (16 `gemini-3.5-flash`, 18 `gemini-3.5-flash-lite`), 249 407 tokens.
- El feed `GET /jobs/{id}/live` se leyó EN VIVO durante la corrida (19→53→119→138→144 eventos en polls sucesivos) desde la subcolección `audit/{job}/live` de Firestore.
- **Cloud Trace:** trace `20c8754e4efda92c0e79a40ee0b7f063` con **191 spans**: 7 `Stage_*`, 16 `Grading_*`, 16 `ArmorScreen`, 16 `FaithfulnessVerification`, 34 `call_llm` + 34 `generate_content` de ADK, anidados bajo el trace id determinístico. URL: `https://console.cloud.google.com/traces/list?project=quanta-gradesync&tid=20c8754e4efda92c0e79a40ee0b7f063`.
- Corrida previa `demo-2b7c2b01-…`: el primer intento murió en AUDIT por un 429 de cuota Vertex → el webhook devolvió 5xx → Pub/Sub redelivery → resume desde checkpoint → **completed** (los dos `Stage_audit`, error y ok, quedaron visibles en el live feed). Auto-recuperación sin intervención.
- Logs JSON estructurados correlacionados: cada línea lleva `logging.googleapis.com/trace` con el mismo trace id.
- IAM aplicado: `roles/telemetry.tracesWriter` y `roles/monitoring.metricWriter` sobre `autocurricula-runner@`.

## Pendiente

- Importar `docs/gcp/monitoring-dashboard.json` en Cloud Monitoring (comando en `docs/gcp/README.md`).
- Los datos demo generados hoy quedan en Firestore; el ritual pre-submit los limpia con `scripts/reset_demo_state.py`.
