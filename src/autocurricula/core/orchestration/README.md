# core/orchestration — Job Execution Graph

## Why an explicit typed graph instead of an ADK SequentialAgent

The pipeline is an ordered list of `StageStep(name, callable)` instances produced by
`build_pipeline(...)`, executed by `JobRunner` — not a `google.adk.agents.SequentialAgent`.

Rationale:

- **The stages are not LLM agents.** `SequentialAgent` composes child `LlmAgent`s that
  talk to a model and pass conversation state through an ADK session/runner. Here only
  two collaborators call a model (the grading evaluator and the curriculum auditor);
  the other stages are deterministic Python orchestrations (GCS staging, risk scoring,
  SIS writes, optimizer triggering). Wrapping them in ADK would add an LLM hop where no
  inference is needed and break the zero-loose-strings contract.
- **Checkpoint/resume needs typed artifacts, not chat transcripts.** ADK session state
  is string-keyed scratch space; this pipeline requires Pydantic stage outputs
  (`FetchOutputs`, `GradingBatchResult`, `AuditOutputs`, `RiskOutputs`, `SISWriteResult`,
  `OptimizeOutputs`) that can be serialized into a `SessionState` checkpoint and
  re-validated on resume via `SessionMemory.get_stage_result`.
- **Google ADK is still the agent runtime where it belongs**: inside
  `agents/grading_agent.py` (ADK `LlmAgent` + Runner + structured output) and the
  calibration/proposer agents used by the optimizer. Orchestration composes those
  agents; it does not need to be one.

## Pipeline

`fetch -> grade -> audit -> risk -> sync -> optimize`

| Step | Completion stage | Output artifact |
| --- | --- | --- |
| `fetch` | `JobStage.FETCHED` | `FetchOutputs(batch, rubric, curriculum_standard)` |
| `grade` | `JobStage.GRADED` | `GradingBatchResult` |
| `audit` | `JobStage.AUDITED` | `AuditOutputs(audits)` |
| `risk` | `JobStage.RISK_ASSESSED` | `RiskOutputs(assessments)` |
| `sync` | `JobStage.SYNCED` | `SISWriteResult` (SIS write + L3 profile/class snapshots) |
| `optimize` | `JobStage.OPTIMIZED` | `OptimizeOutputs(report)` |

## Batch manifest contract

`JobCatalog` resolves the trigger event (`bucket` + `exam_batch_prefix`) to a typed
`BatchManifest` (`batch`, `rubric`, `curriculum_standard`) stored as `batch.json` at the
root of the batch prefix. `LocalJobCatalog` reads it from the GCS staging directory
mirroring `gs://<bucket>/<prefix>/`; `GcsJobCatalog` downloads it from GCS. The manifest
is strict-validated (`rubric_id`/`subject` must match the batch) and aligned with the
event (`class_id`/`subject` must match, `job_id` is forced to the event's `job_id`).

## Checkpoints and resume

`CheckpointStore` persists two documents per job: the `JobRecord` (stage, per-stage
statuses, error, updated_at) and the full `SessionState` (stage results). A step is
skipped on resume only when it is marked `SUCCEEDED` **and** its artifact is present,
which also makes torn writes safe (state is saved before the record). An existing
`COMPLETED` record short-circuits `process(...)` entirely, so Pub/Sub redeliveries of a
finished job are idempotent. The optimize step runs the meta-optimizer cycle when an
optimizer is injected and is skipped without failing the job when no calibration corpus
is provisioned (`FileNotFoundError`).

## Local mode

`build_checkpoint_store` / `build_job_catalog` select the local implementations from
`Settings.local_mode`, so the full pipeline runs without GCP credentials: checkpoints as
JSON files under `<local_data_dir>/jobs/`, the manifest from the local staging tree, and
all agent/evaluator collaborators are injectable scripts.
