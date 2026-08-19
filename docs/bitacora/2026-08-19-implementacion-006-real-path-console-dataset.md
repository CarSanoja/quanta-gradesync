# Dev log — Implementation 006: real Gemini path, operations console, demo dataset, GCP foundations

**Date:** 2026-08-19
**Domain:** Implementation
**Fulfills:** SOL-013 (hackathon execution sprint, phase 1)
**Verification:** offline suite 176 passed; live contract suite 4/4 against Vertex AI (`GRADESYNC_LIVE_TESTS=1 pytest tests/live -m live`).

## Real model path (three production-killing bugs found by live tests)

1. `LlmAgent(temperature=...)` rejected by ADK 2.x (`extra_forbidden`) — every
   structured agent crashed on construction. Fixed via
   `generate_content_config`.
2. Grading tools exposed protocol-typed parameters ADK cannot declare
   (`PydanticSchemaGenerationError`) — 100% of real grading calls died before
   reaching Vertex. Fixed with model-facing adapters (`agents/grading_tools.py`).
3. `CurriculumAuditResult.mappings: dict[str, list[str]]` compiles to JSON-Schema
   `additionalProperties`, which Vertex structured output strips — the auditor
   silently returned empty audits. Fixed with a list-shaped wire model
   (`agents/audit_response.py`) converted back to the persisted contract.

Model reality check: `gemini-3.5-pro` does not exist on Vertex; 3.x models are
served only from location `global`. Defaults are now `gemini-3.5-flash`
(reasoning) + `gemini-3.5-flash-lite` (extraction), new `gemini_location`
setting, and a startup env bootstrap for ADK (`config/genai_env.py`). Measured
cost of grading one handwritten page: ~3.3k input + ~1.3k output/thinking tokens.

## Operations console

`GET /console`: jobs timeline over the checkpoint store, review queue with the
scanned page served through a path-safe endpoint and evidence overlaid,
one-click approve/dismiss, optimizer report. Vanilla JS served by the API, no
build step; bearer-token auth reusing the push token.

## Demo dataset

`scripts/generate_sample_batch.py`: deterministic 8-exam scanned-look batch
(5 solid, 1 wrong-math, 1 illegible, 1 handwritten prompt injection) with
catalog binding, human ground truth for 4 students, and a ready-to-POST push
event. Case matrix and expected behavior per image: `scripts/README.md`.

## GCP foundations

Project `quanta-gradesync` (org account): Firestore, exams bucket with
OBJECT_FINALIZE notification to `exam-batch-ingest`, runtime service account
with least-privilege roles, Artifact Registry, push token in Secret Manager,
$200 budget with alerts. Push subscription pending (needs the Cloud Run URL).

## Process

Work split across two engineering agents with disjoint file ownership
(real path vs. console/dataset), reviewed and committed by the orchestrator as
14 atomic commits; both agent reports were verified against the tree before
integration (live suite re-run, console screenshots, path-traversal probes).
