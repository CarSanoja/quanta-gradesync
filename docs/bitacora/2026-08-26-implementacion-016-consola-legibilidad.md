# Dev log — Implementación 016: legibilidad de la consola

**Fecha:** 2026-08-26
**Dominio:** Implementación
**Cierra:** tres reclamos de Carlos mirando `/console` en vivo, no un bug reportado por un test
**Verificación:** suite offline **610 passed / 8 skipped** (era 601/8; +9, todos de `test_console_assets.py`), `ruff check src tests` en la línea base de **82 errores** preexistentes con cero nuevos, y un walkthrough offline de la consola contra el harness local. Ninguna medición de latencia, costo ni volumen se reclama en esta entrada.

## Contexto — tres reclamos

Ninguna prueba fallaba. Lo que falló fue la lectura de la consola por parte de
un operador que no escribió el código:

1. *"veo muchos elementos que leo y siento que quiero darles click pero nada
   sucede"* — superficies con hover, forma de tarjeta o de pill que no llevan a
   ninguna parte. El costo no es estético: entrena a desconfiar de todo lo que
   sí es clicable.
2. *"Reasoning chains — qué significa eso, qué debo esperar de esa pantalla?"* —
   una etiqueta que describe la implementación (cadenas de razonamiento) y no el
   contenido (un estudiante por tarjeta).
3. *"¿realmente está completa o puede ir más lejos? así con todos los
   procesos"* — el pedido explícito de auditar **todas** las vistas por
   completitud de punta a punta, no sólo la recién construida.

Sobre eso corrieron tres auditorías adversarias: **66 hallazgos** —
21 de afordancias y lenguaje (4 demo-killers), 30 de completitud por vista
(5 demo-killers), 15 del proceso de demo y juez (9 demo-killers); **18
demo-killers** en total. El planificador los convirtió en **55 instrucciones de
cierre repartidas en tres lotes, más 10 rechazadas** (varias instrucciones
absorben hallazgos duplicados, así que los lotes no se suman como hallazgos
distintos).

## Decisiones

**1. La pestaña se llama `Reasoning per student`, y cada pestaña dice qué trae.**
El rename es de copy, no de contrato: `data-live-tab="chains"`,
`#live-tab-chains`, `#live-chain` y `state.tab === "chains"` quedan intactos, de
modo que ningún test de assets ni ningún deep-link se rompe por una decisión de
lenguaje. Debajo de `.live-tabs` vive un único `#live-tab-caption` que
`activateTab` reescribe desde `TAB_CAPTIONS`:

- Fleet activity — *Every agent, every model call and every screen, in the order they happened.*
- Reasoning per student — *One card per student: the armor screen, the grading call, the evidence check, and where the grade landed.*
- Post-run trace — *The span tree persisted to the audit store after the job finished - what ran, how long it took, and what was written.*

Un subtítulo por pestaña en vez de un tour: la pantalla se explica sola en el
momento en que se abre.

**2. Política de-button vs wire, idéntica en los dos lotes de UI.**
Después de esta pasada, todo lo que tenga hover, superficie de tarjeta, forma de
pill/chip o animación de pulso **o recibe un handler o pierde el afordance**.
Nunca `cursor:pointer` sin handler.

Cableados como `<button>` real: las tarjetas de agente del tablero (togglean el
filtro por agente), los pasos de cadena (abren su evento de origen en Fleet
activity), las filas de span del post-run (abren sus atributos), el chip de cola
del topbar (va a Review queue), la celda final de cada fila de estudiante
(toggle de Criteria), el nombre visible del agente en Fleet (deep-link a Mission
control) y la sub-línea `job_id` del SIS (filtra el ledger).

Desbotonados y declarados inertes: las filas de principal de infraestructura en
Fleet (`list-item is-static`, sin hover), un paso de cadena sin evento ancla
(`disabled`), los spans mono de job id / trace id / ruta `gs://` en los detalles
de job y review (texto plano), y los escalares del ticker y del drawer.

**3. Un contrato de navegación explícito en vez de imports cruzados.**
`createLiveController(...)` devuelve `focusLive({ jobId, agentId, studentId,
seq, tab })`, que selecciona el job (difiriendo hasta que el id aparezca en
`/jobs`), fija los filtros cuando la clave está presente, cambia de pestaña y
re-renderiza; es no-op seguro antes de que haya datos. `console.js` publica
`window.goToMissionControl`, `window.goToSisLedger` y `window.goToJobsBatch`.
Las vistas consumen **sólo** esas funciones `window`: ningún módulo de vista
importa `live.js` y ningún `live-*.js` menciona `window.goToMissionControl`. Esa
asimetría es lo que permitió construir los dos lotes en paralelo sin que se
pisaran, y es lo que hace que Fleet → Mission control y Mission control → SIS
sean un click y no una búsqueda manual.

## Alcance por lote

Tres lotes contra un contrato escrito de antemano: propiedad de archivos,
nombres de los módulos nuevos fijados antes de existir (para poder sembrar el
whitelist de `console.py` a ciegas), y `render.js` congelado — todo el texto del
DOM sigue pasando por `textContent` vía `el()`, sin `innerHTML` en ninguna
parte.

- **Mission control** — `console.html`, los `live-*.js`, los módulos nuevos
  `live-focus.js` / `live-students.js` / `live-chain-steps.js`, el whitelist de
  `src/autocurricula/api/console.py` y `tests/api/test_console_assets.py`.
- **Vistas clásicas** — `console.css`, `api.js`, `trace.js`, `views.js`,
  `fleet.js`, `sis.js`, `ingest.js`, `console.js`, los módulos nuevos
  `views-jobs.js` / `views-review.js` / `views-optimizer.js` /
  `views-criteria.js` / `trace-spans.js` / `console-dom.js` /
  `console-review.js`, y `tests/api/test_console.py`.
- **Docs** — `README.md` (sección de observabilidad y el conteo de la suite),
  `docs/submission/judge-guide.md` (los tres nombres de pestaña, el aviso de que
  `Load sample batch` sólo funciona en el servicio desplegado, y el puntero a
  `Post-run trace` para el juez sin cuenta de Google Cloud),
  `docs/runbooks/observability.md` (superficies de la UI, vocabulario del
  post-run, y la nota de que un span de etapa no lleva `agent_id`) y esta
  entrada.

La copia de la UI queda íntegramente en inglés; esta bitácora es el único
artefacto en español.

## Lo que se rechazó, y por qué

- **`A-mc-time-formats-disagree`** — los formatos de hora no coinciden entre
  vistas. El único arreglo real toca `formatDateTime` en `render.js`, archivo
  compartido que ningún lote posee y del que dependen todas las vistas. Valor de
  pulido contra riesgo de regresión cruzada a cinco días del cierre: no se hace.
- **`A-review-bulk-approve-unused`** — fusionado en `B-DA2-R1`: llega al mismo
  endpoint `POST /review/bulk-approve`, pero con la selección segura de
  sólo-retenidos-por-lote que ya expone `/teacher/summary`, en vez de un
  `confirm()` que aprueba todo a ciegas.
- **`A-jobs-criteria-cell-inert`** → `B-DA2-J2` (la misma celda se convierte en
  el toggle de Criteria, lo que además arregla el encabezado de columna y el
  plural `1 criteria`).
- **`A-mc-chain-steps-inert`** → `B-DA2-M2`; **`A-ingest-sample-batch-dead-in-local`**
  → `B-DA2-I2` (una sola guarda de modo local, alimentada por el modo que
  `loadMode()` ya conoce, cubriendo botón, hint y toast).
- **`A-ingest-stale-copy`** — partido, no descartado: la mitad de los `8
  fabricated exams` en `console.html` va al lote de mission control, la mitad del
  toast de `Live trace` va a `B-DA2-I1`.
- **`B-DA2-F1`** — aceptado pero partido por archivo entre los dos lotes;
  **`B-DA2-F2`** — aceptado como **un** mecanismo de filtro por agente, propiedad
  del lote de mission control, con `fleet.js` limitándose a hacer deep-link.
- **`B-DA2-R2`** — aceptado a la baja: sólo el copy del toast y un botón
  `See it in the SIS ledger` cuando la cola queda vacía. El poll de fondo a
  `sisController.load()` en cada aprobación se descartó: el panel de detalle
  normalmente lo reemplaza el siguiente pendiente, no queda vacío.

## Verificación

- **Suite offline: 610 passed / 8 skipped**, 618 tests recolectados. El delta
  contra los 601 de ayer no es código nuevo de producto sino aritmética de
  parametrización: los tres módulos nuevos del lote de mission control
  (`live-focus.js`, `live-students.js`, `live-chain-steps.js`) entran en
  `LIVE_ASSETS`, que alimenta tres tests parametrizados de
  `tests/api/test_console_assets.py` — 3 × 3 = +9. Nada falló y nada se quitó.
- **Lint:** `ruff check src tests` reporta exactamente **82 errores**, la línea
  base preexistente. Cero nuevos.
- **JavaScript:** los diez módulos nuevos pasan `node --check`. Cero
  `innerHTML` en todo `static/`, y `render.js` quedó sin tocar, como decía el
  contrato.
- **Walkthrough offline**, con el harness local en modo local y evaluadores
  scripteados: un batch de 3 estudiantes disparado por el webhook de Pub/Sub
  llegó a `completed` y dejó **32 eventos live**, **16 spans** persistidos sobre
  las 7 etapas (`fetch`, `grade`, `audit`, `risk`, `sync`, `verify`,
  `optimize`) y 1 ítem en la cola de revisión — material suficiente para que las
  tres pestañas de Mission control tengan algo real que dibujar. Las nueve
  superficies que lee la consola respondieron 200: `/jobs`, `/jobs/{id}`,
  `/jobs/{id}/live`, `/jobs/{id}/trace`, `/review/pending`, `/fleet/registry`,
  `/sis/records`, `/optimizer/report` y `/teacher/summary`. Los 28 assets de
  `/console/assets/{name}` se sirven, los diez nuevos incluidos: un módulo
  creado sin whitelistear habría dado 404.
- **La guarda de modo local se verificó en el servidor, no sólo en el botón:**
  `POST /ingest/sample-batch` responde `400` con
  `sample batch copy needs gcp mode; the demo objects live in gcs`, que es
  exactamente lo que el hint nuevo le promete al operador.

Ningún lote commiteó nada.
