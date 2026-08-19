# Dev log — Documentation 001: product docs directory

**Date:** 2026-08-16
**Domain:** Product documentation
**Status:** Published

## What was created

`docs/product/` with two English documents (open-source documentation
standards: status/audience/date header, table of contents, cross-references,
honest limits):

1. **`how-it-works.md`** — "How the GradeSync Engine Works — A Cold Run": a
   detailed, **current-state** explanation (Implementation 003 at the time):
   two planes, cold start with the local/GCP seam table, Pub/Sub trigger,
   zero-form intake (explicit manifest or convention +
   `catalog-defaults.json`), the **seven stages** (including VERIFY with
   bounded rework and OPTIMIZE with convergence tournaments), the L1/L2/L3
   memory hierarchy, the self-evolution engine with anti-gaming, the human
   review API, failure/idempotency semantics, the strict-typing philosophy
   and the file map.
2. **`product-overview.md`** — "The GradeSync Engine as a Product": pitch,
   personas, inputs/outputs matrix, six fundamental guarantees, ROI, a day in
   the life, deployment modes, honest limits and roadmap.
3. **`README.md`** for the directory with the **update policy**: they are
   release artifacts — every implementation cycle MUST update them; history
   lives in the append-only dev log; every claim must be backed by the suite.

## Consistency fixes

- Root README: links `docs/product/`; fixed an inaccuracy (the webhook
  answers `200` accepted/duplicate, not `204` as the Pub/Sub note claimed).

## New operating rule

From this cycle on, every implementation plan includes updating
`docs/product/` as a mandatory step of the cycle.
