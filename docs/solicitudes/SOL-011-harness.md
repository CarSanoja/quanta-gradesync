# SOL-011 — Agent Harness: gobernanza, contención y control (requerimiento verbatim)

**Fecha:** 2026-08-17
**Traza:** [Plan 004](../bitacora/2026-08-17-plan-004-harness.md) → [Implementación 004](../bitacora/2026-08-17-implementacion-004-harness.md) — verificación 139/139
**Estado:** Entregada

Texto del stakeholder, guardado verbatim:

---

ahora un nuevo req a crear y necesito que primero planees como crear ese servicio (que deberia ser generalizable para ser reciclado luego) e integrarlo considerando las sugerencias: Para elevar este motor al nivel de los Agent Harnesses modernos (el andamiaje de gobernanza, contención y control que separa a un modelo estadístico de un agente de producción), debes estructurar el control en tres capas independientes: Execution Harness (contención en caliente), Evaluation Harness (calibración en frío) y Circuit Breakers (seguridad operativa).

## 1. Execution Harness & Control (Plano Caliente / Runtime)

El modelo decide qué intentar; el harness decide qué se permite ejecutar.

**Deterministic Tool-Permission Gate (Rule Pipeline):** El agente jamás interactúa directamente con el SIS, Cloud Storage o Firestore. Cada llamada a herramienta pasa por una tubería de reglas con prioridad: DENY > QUARANTINE > ALLOW. Si una llamada intenta escribir una nota en un estudiante no perteneciente al manifiesto del lote, el harness la bloquea en memoria antes de tocar la red.

**Schema Repair & Mutation Loop:** En lugar de fallar al primer error de tipado o alucinación de campo, el harness intercepta la excepción de Pydantic, genera un sub-prompt correctivo con el validation_error exacto y le da al modelo un máximo de 2 reintentos de autoreparación antes de enviarlo a cuarentena.

**Token & Budget Caps per Job:** Límite estricto de pasos recursivos (N ≤ 4 tool calls por examen) y presupuesto máximo de tokens de salida. Si un examen causa un bucle infinito de razonamiento, el harness aborta la corrida de ese archivo específico y continúa con el resto del lote.

## 2. Evaluation & Calibration Harness (Plano Frío / Offline)

Similar a los harnesses de benchmarking de agentes de código (p. ej. SWE-bench), este arnés mide el desempeño antes y después de cualquier cambio en prompts o pesos:

**Shadow Evaluation (Canary Prompting):** Toda propuesta generada por el MetaOptimizerAgent se corre primero en un ambiente de sombra (shadow mode) contra el CalibrationSet (los exámenes con ground-truth humano).

**Multi-Metric Objective Gate:** Para que un nuevo prompt sea promovido, debe superar un umbral compuesto: QWK ≥ 0.85 ∧ MAE ≤ 0.4 ∧ |Bias| < 0.1.

**Anti-Variance Collapse Sensor:** Si la varianza estándar (σ²) de las notas predichas por el nuevo prompt cae más de un 20% respecto a la varianza del ground-truth, el harness detecta Metric Gaming (el agente intenta acertar el promedio) y rechaza la mutación automáticamente con un RollbackTrigger.

## 3. Safety Circuit Breakers & Governance

Garantías de contención para evitar fallos catastróficos silenciosos:

**Batch Anomaly Breaker:** Si más del 15% de los exámenes de un solo lote caen en estado REQUIRES_HUMAN_REVIEW (confianza < 0.85), el harness suspende la sincronización automática de todo el lote, asumiendo un escaneo defectuoso, rúbrica incorrecta o desalineación de modelo.

**Provenance & Decision Ledger (Auditoría Criptográfica):** Cada registro emitido al SIS lleva adjunto un hash del EvidenceSpan (coordenadas de imagen/PDF + cita textual) y el identificador de versión del prompt utilizado (prompt_version_sha). Cualquier reclamo o auditoría posterior puede rastrear exactamente qué versión del agente y qué fragmento visual generó la calificación.

**Arquitectura de Clases Sugerida para el Harness**

```text
src/core/harness/
├── supervisor.py         # Orquestador del ciclo de vida y control de presupuestos
├── permission_gate.py    # Filtros ALLOW/DENY para herramientas y llamadas de red
├── schema_repair.py      # Loop de auto-corrección de contratos Pydantic
├── circuit_breakers.py   # Detección de anomalías de lote y corte de emergencia
└── eval_harness/         # Torneo de prompts, cálculo QWK/MAE y sensor anti-gaming
```

Con este arnés implementado, el sistema no solo ejecuta tareas complejas, sino que demuestra autonomía responsable, auto-reparación y gobernanza de nivel empresarial.

## Complemento (segunda parte del requerimiento)

**Control en Tiempo de Ejecución (Guardrails Online)** — similar al clasificador de permisos de los agentes de código (read-only by default, approval-gated on mutation):

- **Clasificador de Riesgo de Acción**: Nivel 1 pasivas (leer GCS, consultar L2, parsear esquemas) automáticas; Nivel 2 mutación interna (checkpoints, L3) autónomas condicionadas a parseo estricto; Nivel 3 mutación externa (SIS/LMS, notificar directivos) requieren Confidence Gate ≥ 0.85, si no la superan se desvían a REQUIRES_HUMAN_REVIEW y se aborta la llamada al conector HTTP.
- **Bounded Tool Budgets & Circuit Breakers**: máximo 2 intentos de autoreparación de esquema (SchemaRepairBudget); aislamiento de fallo (Blast-Radius Containment) — el fallo de un examen en un lote de 40 no aborta el job de Pub/Sub, solo aísla el registro corrupto y continúa con los otros 39.

**Faithfulness Verifier (Clasificador de Fidelidad y Anclaje Semántico)**: capa determinista ligera que verifica el EvidenceSpan antes de aceptar el GradingResult — exact-match & span verification: si la cita textual no existe literalmente en el texto transcrito/extraído de esa página, es una alucinación → confidence_score a 0.0 y cuarentena.

**Evaluation Harness Fuera de Línea (Dev-Time & Meta-Optimizer Gate)**: ingesta de Golden Dataset (CalibrationSet), ejecución concurrente en sandbox aislado, colector de trazas, suite de métricas deterministas (MAE, QWK, directional bias, variance collapse/gaming detector); pasa todos los gates → promoción a PromptRegistry; falla alguno → rollback inmediato + log. Dataset de "Goldens" inmutable (20–50 exámenes históricos calibrados por comité de expertos). Anti-Regression Gate en CI/CD: ningún PR o despliegue se ejecuta si QWK < 0.80 o aumenta el sesgo sistemático sobre el golden dataset.

**Estructura concreta sugerida:**

```text
src/core/harness/
├── action_classifier.py    # Clasifica llamadas a tools por nivel de riesgo
├── circuit_breaker.py      # Presupuestos de tokens, tiempos máximos y reintentos
├── faithfulness_gate.py    # Validador de existencia y exactitud del EvidenceSpan
└── eval_runner.py          # Runner de evaluación contra el dataset de calibración
```

Con este esquema de Harnessing, el sistema pasa de ser un simple agente autónomo a un agente con gobernanza de nivel enterprise.
