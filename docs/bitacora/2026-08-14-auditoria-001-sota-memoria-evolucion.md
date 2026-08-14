# Bitácora — Auditoría 001: nivel SOTA de memoria y auto-mejora

**Fecha:** 2026-08-14
**Dominio:** Auditoría técnica
**Conclusión:** arquitectura SOTA-pattern completa; algoritmos reales; 3 simplificaciones conscientes → Plan 002.

## Memoria

### L1 — Session State (`core/memory/session_memory.py`) — SOTA ✅
Estado tipado por job (`stage_results`/`stage_statuses`), re-validado con `TypeAdapter` al restaurar de checkpoint — el resume post-crash es type-safe. Más estricto que el patrón de dict sin tipar.

### L2 — Vector Search (`core/memory/vector_memory.py`) — SOTA con matiz ⚠️
- Local: TF-IDF real (IDF suavizado, coseno disperso, desempate determinista, corte en score 0).
- GCP: `find_nearest` de Firestore con COSINE — vector search administrado de verdad.
- **Matiz**: embedder por defecto es *feature hashing* SHA-256 → léxico, no semántico. Inyectable, pero sin embeddings reales los sinónimos no se agrupan.

### L3 — Managed Cloud Memory (`persistent_memory.py`, `manager.py`) — SOTA ✅
Memoria como conocimiento curado (agregados con schema), no log de chat. Backends local JSON y Firestore. Escritura de outcomes confirmados.

## Self-Evolving

Loop completo en producción (etapa OPTIMIZE): calibración (MAE/QWK/bias) → proposer (LLM estructurado / heurístico local) → re-evaluación sobre el mismo ground truth → `AntiGamingValidator` (constant-output, variance-collapse con piso `truth_std × 0.75`, ground-truth-contact) → promoción versionada con rollback y persistencia en L3.

El anti-gaming **excede** el patrón estándar de los codelabs de ADK.

## Gaps (rankeados por impacto/costo)

1. **Embeddings semánticos en L2** — conectar Vertex text-embeddings al embedder inyectable. Costo bajo, impacto alto en recuperación curricular.
2. **Evolución de 1 candidato** — hoy incumbente vs 1 retador; SOTA pleno = torneo de N mutaciones, promover la mejor.
3. **Solo evoluciona el prompt de grading** — `auditor-v1` está sembrado pero el motor no lo evoluciona.
4. Sin shadow rollout de variantes aceptadas (futuro).
5. Sin scheduler nocturno propio (futuro).
6. Sin drift per-criterio en producción (futuro).
