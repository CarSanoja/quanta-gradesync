# Bitácora — Feedback 001: fricción operativa, gobernanza y ROI

**Fecha:** 2026-08-13
**Dominio:** Feedback de producto
**Fuente:** Stakeholder (revisión de la entrada "producto: entradas y salidas")
**Estado:** Aceptado — planificado en `2026-08-17-plan-001`

## 1. El punto ciego de la fricción operativa: ¿quién llena el manifiesto?

**Problema:** si el docente tiene que crear un JSON o llenar un formulario por cada lote, se rompe la promesa de "el docente sube archivos y desaparece".

**Mejora pedida:** el manifiesto debe poder **inferirse automáticamente** por convención de nombres de archivo/carpetas en el bucket (ej. `2026_Matematicas_10A_Parcial1.pdf`) o mediante carátula preimpresa con código QR/OCR leída en la etapa FETCH.

## 2. La garantía de gobernanza: cuarentena por confianza (confidence-gated quarantine)

**Problema:** en K-12 formal, escribir el 100% de las notas directo al SIS sin validación previa genera rechazo institucional (miedo a litigios o reclamos de apoderados).

**Mejora pedida:** garantía explícita — "si la confianza de extracción multimodal o la nitidez de la evidencia cae por debajo del **85%**, la nota no se sincroniza directo: queda en estado `REQUIRES_HUMAN_REVIEW` con la página y el recorte visual exacto pre-resaltado para que el docente la apruebe con 1 clic".

## 3. Métricas de ROI cuantitativo

- **Ahorro de tiempo docente:** de ~12 horas semanales de corrección manual a cero transcripción y solo ~10 minutos de revisión de excepciones.
- **Time-to-feedback:** reducción del ciclo de retroalimentación de 14 días a menos de 10 minutos tras subir el escaneo.

## 4. Versión optimizada del pitch (para README)

**Elevator pitch:** "Entra un lote de exámenes escaneados; salen calificaciones auditadas en el SIS, mapas de cobertura curricular y alertas tempranas de deserción. El docente no usa una app ni aprende interfaces: deposita archivos y recupera sus tardes. Es infraestructura de backoffice puro."

**Matriz de flujos de entrada (nueva):**

| Entrada | Origen | Frecuencia |
|---|---|---|
| Lote de exámenes escaneados (PDFs/imágenes manuscritas) | Docente o secretaría | Por evaluación |
| Metadatos del lote (materia, grado, rúbrica activa) | **Auto-inferido por convención de ruta o código de lote** | Automático por evento |
| Rúbricas y estándar curricular nacional | Coordinación pedagógica | 1 vez por periodo |
| Muestras de calibración (ground-truth humano) | Evaluaciones históricas validadas | Periódico (alimenta auto-mejora) |
| Credenciales y conectores SIS/LMS | TI / Administración | Setup inicial único |

**Garantías fundamentales (nueva formulación):**

1. **Idempotencia transaccional:** aunque Pub/Sub entregue el mensaje múltiples veces, un examen jamás se duplica ni se computa dos veces en el SIS.
2. **Defendibilidad absoluta:** toda calificación incluye un `EvidenceSpan` con cita textual y número de página; los reclamos se responden con evidencia del propio manuscrito.
3. **Escalación por umbral de confianza:** respuestas ambiguas o con caligrafía ilegible no se adivinan: entran en cuarentena para validación rápida del docente.
4. **Riesgo determinista y explicable:** alertas basadas en tendencias matemáticas (z-scores, pendientes longitudinales en L3), no en opiniones libres de un LLM.
5. **Auto-mejora anti-gaming:** el optimizador solo promueve variantes que mejoren el acuerdo humano (QWK/MAE), bloqueando colapso de varianza o notas promedio artificiales.
6. **Tolerancia a fallos de larga duración:** checkpoints persistentes por etapa; el flujo se reanuda exactamente en la etapa pendiente sin recomputar trabajo previo.
