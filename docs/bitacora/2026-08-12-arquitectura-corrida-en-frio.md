# Bitácora — Arquitectura y flujo: corrida en frío

**Fecha:** 2026-08-12
**Dominio:** Arquitectura técnica
**Estado:** Implementado y verificado (53/53 tests)

## La idea en una frase

No es un chat: es una **cinta transportadora tipada**. Un evento externo (subida de exámenes) empuja un "job" por seis etapas, cada etapa habla con la siguiente **solo a través de contratos Pydantic estrictos**, y en paralelo corre un segundo plano lento que mejora los prompts del sistema sin poder hacer trampa.

## Diagrama de los dos planos

```text
          ┌──────────── PLANO CALIENTE (por job, segundos/minutos) ────────────┐
Docente ─► GCS ─► Pub/Sub ─► POST /webhooks/pubsub ─► JobRunner
sube PDFs                          (token + idempotencia)      │
                                                             ▼
            FETCH ─► GRADE ─► AUDIT ─► RISK ─► SYNC ─► OPTIMIZE ─► COMPLETED
              │        │         │       │       │        │
           staging  Gemini    Gemini   stats   SIS API  (dispara
           files    3.5 Pro   Flash    puras   + L3     el plano
                    + L2      + L2     + L3    write     frío)
          └──────────────────────────────────────────┬─────────┘
                                                      ▼
          ┌────────── PLANO FRÍO (periódico, autoevolución) ──────────┐
          CalibrationSet (ground truth humano) ─► MAE/QWK/bias ──────┐
          Proposer LLM propone nuevo prompt ─────────────────────────┤
          Candidato se re-evalúa ─► AntiGamingValidator ─► ¿aceptar? │
          └───────────────────────────────────────────────────────────┘
```

## Arranque en frío del servicio (una vez)

El `lifespan` de FastAPI construye el `AppContainer` (`src/autocurricula/api/dependencies.py`): lee `Settings` y elige implementación por costura según `local_mode`:

| Costura | Local (sin credenciales) | GCP |
|---|---|---|
| Archivos de examen | `LocalStagingFetcher` | `GcsFetcher` |
| Memoria vectorial L2 | `LocalVectorMemory` (TF-IDF) | `FirestoreVectorMemory` |
| Memoria persistente L3 | `LocalPersistentStore` (JSON) | `FirestorePersistentStore` |
| Escritura SIS | `LocalSISConnector` (jsonl) | `HttpSISConnector` |
| Checkpoints | `LocalCheckpointStore` | `FirestoreCheckpointStore` |

La lógica de negocio es idéntica en ambos modos; solo cambian los transportes.

## Etapas de la corrida

1. **Disparador.** Subida al bucket → Pub/Sub → push a `POST /webhooks/pubsub` (`webhooks.py:61`). Valida bearer token en tiempo constante, decodifica el envelope a `PubSubJobEvent` estricto, verifica idempotencia contra el checkpoint store (`duplicate` → 200 sin reprocesar), lanza `runner.process()` en background y responde `accepted` de inmediato.
2. **FETCH.** `JobCatalog.load_manifest(event)` carga manifiesto del lote (archivos, rúbrica, estándar curricular); el fetcher materializa archivos. Salida tipada: `ExamBatch` + `Rubric` + `CurriculumStandard`.
3. **GRADE.** La rúbrica se sube a L2 y se recupera contexto top-5; `asyncio.gather` califica todas las entregas concurrentemente con `AdkGradingEvaluator` (Gemini 3.5 Pro multimodal, output schema `GradingResult`, cada puntaje cita `EvidenceSpan`; retry de reparación si no parsea).
4. **AUDIT.** Query con las competencias del ministerio → L2 → Gemini Flash mapea criterios a códigos de competencia: `covered_codes` vs `missing_codes`.
5. **RISK.** Sin LLM: carga perfiles episódicos de L3 y corre z-scores, tendencia, colapso de confianza y tasa de faltantes → `RiskAssessment` explicable.
6. **SYNC.** `SISGradeRecord` → conector SIS; `persist_outcomes` escribe de vuelta a L3 (`TermSnapshot` por estudiante, `ClassCompetencySnapshot` por competencia).
7. **OPTIMIZE.** Dispara un ciclo del meta-optimizer y marca `COMPLETED`.

Tras cada etapa: checkpoint de sesión + record. Muerte de instancia → Pub/Sub reintenta → el runner restaura la sesión, salta etapas `SUCCEEDED` y continúa (`runner.py:71-74`).

## Plano frío: autoevolución con candado

`MetaOptimizerEngine.run_iteration` (`optimizer_engine.py:52`):

1. Evalúa el variante actual contra `CalibrationSet` (ground truth humano) → `CalibrationMetrics` (MAE, QWK, bias).
2. Proposer (Gemini Flash, `ProposalSchema` estricto) propone mutación con justificación.
3. El candidato se re-evalúa sobre el mismo ground truth.
4. `AntiGamingValidator`: rechaza colapso de varianza, salidas constantes, mejoras sin contacto con ground truth.
5. Solo si pasa: `PromptRegistry.register` promueve con version bump (con rollback disponible).

Semántica: el optimizador optimiza acuerdo con humanos, no estética de la distribución.

## Semántica de las tres memorias

- **L1 — SessionMemory:** mesa de trabajo efímera del job, serializable a checkpoint.
- **L2 — VectorMemory:** "¿qué es relevante ahora?" — rúbricas y competencias por significado.
- **L3 — PersistentStore:** "¿qué recuerdo del estudiante en el tiempo?" — perfiles episódicos y snapshots de clase; convierte RISK en detección de trayectoria.

Principio rector: **cada flecha del diagrama es un modelo Pydantic con `extra=forbid`**. Ningún agente inventa campos; la basura explota ruidosamente, nunca se propaga silenciosamente.
