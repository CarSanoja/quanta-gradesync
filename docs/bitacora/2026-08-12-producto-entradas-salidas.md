# Bitácora — El GradeSync como producto: qué entra y qué sale

**Fecha:** 2026-08-12
**Dominio:** Producto / valor
**Estado:** Vigente (revisado por feedback 001 — ver entrada de feedback)

## Elevator pitch

**Entra un paquete de exámenes escaneados; salen notas escritas en el sistema del colegio, alertas de riesgo y un mapa de competencias de la clase.** El docente no "usa" una app: sube archivos y desaparece del flujo. Es backoffice puro — cero chat, cero interfaces que aprender.

## Qué entra

| Entrada | Quién la provee | Frecuencia |
|---|---|---|
| Lote de exámenes escaneados (PDFs/imágenes, manuscritos) | Docente o secretaría académica | Cada evaluación |
| Manifiesto del lote — clase, asignatura, rúbrica, estándar curricular | El colegio (plantilla) | Cada evaluación |
| Rúbricas vigentes y estándar de competencias del ministerio | Coordinación académica | Una vez por periodo |
| Muestras de calibración — exámenes calificados por humanos (ground truth) | Los docentes | Ocasional |
| Credenciales y endpoints — SIS, bucket, topic Pub/Sub | TI del colegio | Una vez (setup) |

## Qué sale

**Para el docente:**
- Nota por criterio con evidencia citada (página + cita textual del manuscrito)
- Feedback redactado por entrega
- Turnaround de minutos, no horas

**Para coordinación académica:**
- Conciliación curricular automática (competencias cubiertas vs huérfanas)
- Alertas tempranas de deserción con drivers explicables e intervenciones sugeridas
- Mapa de dominio de la clase por competencia

**Para el SIS / backoffice:**
- Registros de notas ya escritos, con códigos de competencia — cero transcripción

**Para el propio motor:**
- Reportes de calibración: versión de prompt activa, MAE/QWK/bias contra humanos, mutaciones rechazadas y por qué

## Garantías de producto

1. Nunca duplica una nota (idempotencia de job).
2. Nunca pierde un lote a medias (reanudación por checkpoint).
3. Toda nota es defendible (cita evidencia del propio trabajo).
4. El riesgo no es caja negra (estadística determinista).
5. Mejora pero no hace trampa (gate anti-gaming del optimizador).
6. Nada se degrada silenciosamente (contratos estrictos).

## Límites honestos

- Calidad de salida = función de la calidad de rúbricas y escaneos.
- El loop de mejora requiere ground truth humano.
- Ilegibilidad genuina → fallo explícito y marcado; el producto no inventa lectura.

**En una línea:** convierte horas de calificación manual + transcripción + cruce curricular + detección a ojo de riesgo en **un upload**, con recibo auditable de cada decisión.
