# SOL-012 — Enterprise observability, forensic traceability and agentic self-healing

**Date:** 2026-08-17
**Trace:** [Plan 005](../bitacora/2026-08-17-plan-005-observability-self-healing.md) → [Implementation 005](../bitacora/2026-08-17-implementacion-005-observability-self-healing.md)
**Status:** Delivered

Stakeholder request, stored verbatim (original wording in Spanish):

---

Para dotar al motor de observabilidad enterprise, trazabilidad forense y auto-recuperación agéntica (Self-Healing) sin caer en bucles infinitos, el diseño debe separar la telemetría determinista del agente reparador.

## 1. Arquitectura de Trazabilidad & Observabilidad (OpenTelemetry + Spans Agénticos)

Cada ejecución de un lote genera un árbol de trazas (Trace) estructurado donde cada etapa y llamada a sub-agentes es un Span con metadatos tipados. Trace Context Propagation: el trace_id se genera en el webhook de Pub/Sub y viaja por todas las etapas y llamadas a herramientas (L1 → L2 → L3). Atributos de Span obligatorios: `gen_ai.system` (google_gemini, Gemini 3.5 Pro/Flash), `gen_ai.usage.tokens` (input/output tokens y latencia por invocación), `agent.stage` (FETCH | GRADE | AUDIT | RISK | SYNC | OPTIMIZE), `evidence.span_match` (valida si el span textual existía en el documento). Árbol de ejemplo:

```text
[Trace: job_9f82a1]
 ├── [Span: FetchManifestAndFiles] (120ms)
 ├── [Span: L2_VectorRetrieval_Rubrics] (85ms)
 ├── [Span: AdkGradingEvaluator_Student_A] (1420ms, tokens: 2150)
 │    └── [ToolCall: search_rubrics] (45ms)
 ├── [Span: FaithfulnessVerification] (12ms) -> PASS
 └── [Span: SIS_Sync] (210ms)
```

## 2. Secuencia de Auto-Recuperación (Self-Healing Pipeline)

Cuando una etapa falla, el sistema no aborta ciegamente ni delega el control total a un LLM sin límites: Árbol de Decisión de Fallos — error sintáctico/schema → SchemaRepairAgent (válido en ≤2 retries → reanuda; inválido → aísla examen a cuarentena manual); error semántico/API → Triage Classifier (transitorio 429/503 → backoff exponencial + fallback a Gemini Flash; fallo fatal/OOM → checkpoint save + alerta Sentry/Cloud Trace).

**Los 3 agentes de mitigación:**
- **SchemaRepairAgent** (auto-corrección sintáctica): toma el JSON roto, el error exacto de Pydantic y el esquema estricto, e instruye una re-generación quirúrgica en un solo paso.
- **ModelFallbackController** (resiliencia ante degradación de API): si Gemini 3.5 Pro tiene latencia extrema (>15s) o errores 429, conmuta el ítem a Gemini 3.5 Flash con prompt simplificado y reduce el confidence_score para marcar el ítem a revisión.
- **StateRollbackManager** (idempotencia en fallos de red): si la escritura al SIS falla a mitad de un lote, revierte la transacción local, almacena los IDs fallidos en una cola de Dead Letter interna y reintenta únicamente las transacciones huérfanas en la siguiente ventana de ejecución.

## 3. Estructura sugerida

```text
src/core/
├── telemetry/
│   ├── tracer.py               # OpenTelemetry + Cloud Trace exporter
│   ├── metrics_collector.py    # tokens, latencias P95, tasas de error por etapa
│   └── audit_logger.py         # JSON forense estructurado
└── resilience/
    ├── circuit_breaker.py      # ventanas de error y budgets
    ├── repair_agent.py         # sub-agente corrector de esquemas
    └── dead_letter_store.py    # aislamiento de exámenes no recuperables
```

## 4. Garantías de seguridad del auto-healing

- **Budget cap estricto:** máximo 2 intentos de reparación agéntica por examen; tras el segundo fallo se aborta la auto-recuperación y el examen entra a la lista de excepciones.
- **Inmutabilidad del historial:** el agente de auto-reparación puede corregir formatos o reintentar llamadas, pero jamás alterar el registro de eventos original (audit trail) ni mutar L3 sin validación previa del gate.
