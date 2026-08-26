# Dev log — Implementación 017: evidencia verificada en producción y consola cerrada

**Fecha:** 2026-08-26 · **Rama:** main · **Revisión Cloud Run:** `autocurricula-gradesync-00021-rk5` (imagen `:4238005`)

Cierra dos hilos abiertos por la [implementación 016](2026-08-26-implementacion-016-consola-legibilidad.md) y la [015](2026-08-26-implementacion-015-telemetry-produccion.md): el estado `unchecked` permanente del verificador de evidencia en producción, y los cinco hallazgos que sobrevivieron al re-ataque de la consola.

## Problema

Con scans manuscritos reales no existe texto de referencia (el sidecar `.txt` solo lo produce el generador del batch demo), así que `FaithfulnessVerification` reportaba `unchecked` para todos los alumnos en producción: el check existía pero nunca podía ejecutarse.

## Diseño

- **Agente #12, `evidence-transcriber`** (`gemini-3.5-flash-lite`, etapa GRADE, capacidad `llm.invoke`, principal propio): antes de calificar, transcribe cada página verbatim. Segunda lectura independiente — nunca el modelo calificador validándose a sí mismo.
- **Matching difuso** en `core/harness/faithfulness.py`: cobertura del substring común más largo ≥ `faithfulness_match_threshold` (0.75); citas de menos de 12 caracteres normalizados exigen contención exacta. Los sidecars conservan precedencia estricta (`CompositeTextProvider`); una transcripción fallida degrada a `unchecked` y jamás bloquea la calificación.
- **Insensible a whitespace**: la primera corrida de producción marcó `failed` a mateo-quintero porque el grader escribió `20/60 = 4/3 h` y la transcripción decía `20 / 60 = 4 / 3 h`. Las citas se comparan sin espacios antes de cualquier cobertura; solo las diferencias de contenido fallan (`4238005`).
- **Reintentos con backoff** (`agents/gemini_retry.py`): todos los caminos Gemini (agentes ADK y el cliente crudo del auditor) reintentan 429/5xx con backoff exponencial (5 intentos, 2 s → 30 s). Dos corridas de producción de hoy murieron en AUDIT/VERIFY por `RESOURCE_EXHAUSTED` y se recuperaron por redelivery de Pub/Sub; el reintento in-process evita mostrar `failed` durante minutos.

## Evidencia de producción

| Corrida | Revisión | Resultado |
|---|---|---|
| `demo-798a4f82` | 00020-vsr | 15 `verified` / 1 `failed` (falso positivo por espaciado); 429 en VERIFY → redelivery → completed; 16 transcripciones |
| `demo-fffab2a8` | 00021-rk5 | **completed en 84 s, 0 errores, 16/16 `verified`**, 50 llamadas LLM (275 754 tokens), 14 synced / 2 quarantined (camila-rios ilegible, julian-pardo inyección). Trace `df545898e7e4202537c04aad909343f1` |

Registro de flota en producción: 12 agentes, 12 wired, 15 principales; `evidence-transcriber` aparece como wired. Test live `tests/live/test_transcription.py` (2 passed contra Vertex): encabezado impreso y factorización manuscrita verifican; una cita fabricada no.

## Consola: supervivientes del re-ataque cerrados (`da6795d`)

`unchecked` se muestra neutro y explicado ("Evidence check: no reference text to verify against"); nuevo tipo de evento `transcription` en el ticker y paso "Page transcription" en cada cadena por alumno; el deep link Fleet → Mission control conserva el filtro de agente en la primera selección automática; el SIS ledger filtra antes de la primera petición; el botón de liberación por regla de lote nombra qué libera y muestra la regla; cada tarjeta de alumno puede acotar el ticker a ese alumno; un fallo transitorio del detalle se reintenta en el siguiente poll; controlador muerto eliminado de `trace.js`; diálogo de colisión separado a `ingest-collision.js`. Lección de proceso: `node --check archivo.js` no detecta errores en módulos ES en Node 24 — la puerta real es `node --input-type=module --check < archivo`.

## Verificación

Suite offline **653 passed / 10 skipped**; ruff en la línea base de 82; 38 módulos JS con el check real. Documentación, diagrama de flota, slide, pitch y PDF dicen doce componentes (ocho con modelo, cuatro determinísticos) y 653 tests.
