# Bitácora — Documentación 001: directorio de producto

**Fecha:** 2026-08-16
**Dominio:** Documentación de producto
**Estado:** Publicado

## Qué se creó

`docs/product/` con dos documentos en inglés (estándar de documentación open source:
encabezado de estado/audiencia/fecha, tabla de contenidos, referencias cruzadas,
límites honestos):

1. **`how-it-works.md`** — "How the GradeSync Engine Works — A Cold Run": explicación
   detallada y **actualizada al estado actual** (Implementación 003): dos planos,
   arranque en frío con tabla de costuras local/GCP, trigger Pub/Sub, intake sin
   formularios (manifiesto explícito o convención + `catalog-defaults.json`), las
   **siete etapas** (incluye VERIFY con re-trabajo acotado y OPTIMIZE con torneos de
   convergencia), jerarquía de memoria L1/L2/L3, motor de autoevolución con
   anti-gaming, API de revisión humana, semántica de fallas/idempotencia, filosofía
   de tipado estricto y mapa de archivos.
2. **`product-overview.md`** — "The GradeSync Engine as a Product": pitch, personas,
   matriz de entradas/salidas, 6 garantías fundamentales, ROI, un día en la vida,
   modos de despliegue, límites honestos y roadmap.
3. **`README.md`** del directorio con la **política de actualización**: son artefactos
   de release — cada ciclo de implementación DEBE actualizarlos; la historia vive en
   la bitácora (append-only); toda afirmación debe estar respaldada por la suite.

## Ajustes de consistencia

- README raíz: enlaza `docs/product/`; corregida una inexactitud (el webhook responde
  `200` accepted/duplicate, no `204` como decía la nota de Pub/Sub).

## Regla operativa nueva

A partir de este ciclo, todo plan de implementación incluye la actualización de
`docs/product/` como paso obligatorio del ciclo.
