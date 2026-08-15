# Bitácora — Auditoría 002: ¿es un sistema agéntico?

**Fecha:** 2026-08-15
**Dominio:** Auditoría conceptual
**Pregunta:** ¿puede pensar, ejecutar acciones, verificar si se cumplió la meta y seguir en un loop hasta terminar de la mejor forma posible?

## Conclusión

**Híbrido: workflow determinista con islas agénticas.** El loop agéntico completo existe hoy en el plano frío (auto-mejora); en el plano caliente la ejecución es un DAG fijo con gates de verificación distribuidos pero sin verificador de meta ni re-trabajo.

## Lo que existe

1. **Loop de herramientas (micro-agencia)**: agentes ADK eligen tools (fetch, vector search), observan y deciden el siguiente paso.
2. **Loop de reparación**: salida LLM que viola el contrato → retry con instrucción de corrección.
3. **Loop de auto-mejora (plenamente agéntico)**: estado (linaje de prompts en L3) → meta (MAE/QWK vs humanos) → acción (torneo de N mutaciones) → verificación (mejora + anti-gaming) → aprendizaje persistido. El sistema dirige su propia mejora.
4. **Loop de resiliencia**: checkpoints + reintento Pub/Sub + resume — itera hasta terminar, por infraestructura.

## Lo que falta en el plano caliente

1. **Verificador de meta**: nadie evalúa tras SYNC si el job logró su misión.
2. **Re-trabajo dirigido**: baja confianza masiva no dispara re-intento con otra estrategia.
3. **Convergencia autónoma**: el optimizador corre un torneo por disparo; no itera hasta converger.

## Por qué es (en parte) una decisión de diseño

En corrección K-12 el camino caliente debe ser reproducible, auditable y de costo predecible; la agencia se concentra donde suma (juicio multimodal, auto-mejora) y se acota con gates (schemas, anti-gaming, umbral de confianza). Un agente libre en el pipeline principal sería un pasivo legal, no una feature.

## Resolución

Plan 003 cierra los gaps 1–3 **sin romper la tesis**: verificación y re-trabajo acotado y trazable; convergencia con presupuesto. El planner por job queda diferido: el DAG fijo es la postura auditable correcta para este dominio.
