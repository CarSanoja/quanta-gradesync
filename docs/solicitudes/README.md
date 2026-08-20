# Registro de solicitudes (requirements traceability)

Cada solicitud del stakeholder queda registrada aquí con su traza completa:
**solicitud → plan → implementación → verificación**. Las solicitudes se numeran
`SOL-NNN` y son inmutables; los artefactos asociados viven en la
[bitácora](../bitacora/README.md) y en [docs/product](../product/README.md).

**Regla operativa:** toda nueva solicitud del usuario recibe su entrada aquí antes
de planificar; si la solicitud llega en texto extenso, se guarda verbatim en su
propio archivo `SOL-NNN-*.md`.

| ID | Fecha | Solicitud (resumen) | Traza | Estado |
|----|-------|---------------------|-------|--------|
| [SOL-001](SOL-001-spec.md) | 2026-08-11 | Especificación fundacional del motor (contexto, pilares, memoria, evolución, workflows) | [README raíz](../../README.md) → [`docs/product/`](../product/README.md) | Entregada |
| [SOL-002](SOL-002-workflow-inicial.md) | 2026-08-11 | Lanzar un workflow e implementar el motor completo según la especificación | Build inicial de 13 agentes (2 corridas, 464 tool calls) → 82/82 tests. Retroactiva: no tuvo entrada de bitácora por ser anterior a ella | Entregada |
| SOL-003 | 2026-08-12 | Explicación semántica de arquitectura y flujo (corrida en frío) | [Bitácora: arquitectura](../bitacora/2026-08-12-arquitectura-corrida-en-frio.md) | Entregada |
| SOL-004 | 2026-08-12 | Explicación como producto: qué entra y qué sale | [Bitácora: producto](../bitacora/2026-08-12-producto-entradas-salidas.md) | Entregada |
| SOL-005 | 2026-08-13 | Documentar como bitácora + feedback: manifiesto auto-inferido, cuarentena por confianza (85%), ROI | [Feedback 001 (verbatim)](../bitacora/2026-08-13-feedback-001-friccion-gobernanza-roi.md) → [Plan 001](../bitacora/2026-08-13-plan-001-manifiesto-cuarentena.md) → [Impl. 001](../bitacora/2026-08-13-implementacion-001-manifiesto-cuarentena.md) (82/82) | Entregada |
| SOL-006 | 2026-08-14 | Auditoría SOTA de Agent Memory y Self-Evolving Agent | [Auditoría 001](../bitacora/2026-08-14-auditoria-001-sota-memoria-evolucion.md) | Entregada |
| SOL-007 | 2026-08-14 | Planificar e implementar gaps 1–3 (embeddings semánticos, torneo de N, evolución del auditor) | [Plan 002](../bitacora/2026-08-14-plan-002-embeddings-torneo-auditor.md) → [Impl. 002](../bitacora/2026-08-14-implementacion-002-embeddings-torneo-auditor.md) (99/99) | Entregada |
| SOL-008 | 2026-08-15 | ¿Es un sistema agéntico? (pensar/actuar/verificar/iterar) | [Auditoría 002](../bitacora/2026-08-15-auditoria-002-loop-agenticio.md) | Entregada |
| SOL-009 | 2026-08-15 | Implementar el cierre agéntico (verificador de meta + convergencia) | [Plan 003](../bitacora/2026-08-15-plan-003-cierre-agenticio.md) → [Impl. 003](../bitacora/2026-08-15-implementacion-003-cierre-agenticio.md) (107/107) | Entregada |
| SOL-010 | 2026-08-16 | Directorio de documentación de producto (2 docs en inglés, estándar OSS, actualizados por ciclo) | [Documentación 001](../bitacora/2026-08-16-documentacion-001-producto.md) → [`docs/product/`](../product/README.md) | Entregada |
| [SOL-011](SOL-011-harness.md) | 2026-08-17 | Agent Harness: execution/evaluation/breakers en tres capas (texto verbatim guardado) | [Plan 004](../bitacora/2026-08-17-plan-004-harness.md) → [Impl. 004](../bitacora/2026-08-17-implementacion-004-harness.md) (139/139) | Entregada |
| [SOL-012](SOL-012-self-healing.md) | 2026-08-17 | Observabilidad enterprise, trazabilidad forense y self-healing acotado (texto verbatim guardado) | [Plan 005](../bitacora/2026-08-17-plan-005-observability-self-healing.md) → [Impl. 005](../bitacora/2026-08-17-implementacion-005-observability-self-healing.md) (158/158) | Entregada |
| SOL-013 | 2026-08-19 | Sprint de ejecución para el hackathon: ruta real a Gemini verificada en vivo, consola de operaciones, dataset demo, fundaciones GCP | [Impl. 006](../bitacora/2026-08-19-implementacion-006-real-path-console-dataset.md) (176 + 4 live) | Entregada |
| SOL-014 | 2026-08-20 | Sprint fase 2 en workflow paralelo: Model Armor + confianza por legibilidad, SIS visible, panel de ingesta, live trace, ack-on-success | [Impl. 007](../bitacora/2026-08-20-implementacion-007-armor-sis-ingest-ack.md) (258 + 2 live armor) | Entregada |
