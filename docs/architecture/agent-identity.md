# Per-agent identity and capability enforcement

This document describes the identity model of the GradeSync fleet: which
principal each agent acts as, what that principal is allowed to do, where the
rule is enforced, and which parts of the model are enforced **in process** by
this repository versus which parts require **cloud IAM** that an operator must
apply. It is deliberately explicit about that boundary, because the two give
very different guarantees.

## 1. What changed and why

Before this change the fleet had one identity: the Cloud Run runtime service
account. Every agent — grading, audit, armor, the optimizers — executed with the
union of every permission any of them needed, and nothing in the code could tell
which agent had performed a given action. "Per-agent identity" was a claim the
system could not support.

The model below makes identity real in the only place a single-service
deployment can make it real without re-architecting into microservices:

1. every agent maps to a **declared principal** with a **least-privilege
   capability set**;
2. every external action is **checked in memory against that capability set
   before the network call**, denied with an auditable record if it is out of
   scope;
3. the agent identity is carried into **telemetry spans** and the **provenance
   ledger**, so an audit can attribute an action to a principal;
4. where a distinct GCP service account is genuinely warranted — the SIS writer,
   the only agent that mutates a system of record outside our control — the code
   path to **impersonate a dedicated service account** exists and is switched on
   by configuration.

## 2. The principals

`GET /fleet/registry` returns this table derived from the running configuration.
Fourteen principals: one per agent, plus three infrastructure principals that do
the work no single agent owns.

### Agent principals

| Principal | Agent | Capabilities |
|---|---|---|
| `agent://grading-agent` | Grading agent | `llm.invoke` |
| `agent://curriculum-auditor` | Curriculum auditor | `llm.invoke`, `firestore.read` |
| `agent://risk-detector` | Risk detector | `firestore.read` |
| `agent://armor-screener` | Armor screener | `llm.invoke` |
| `agent://second-opinion-evaluator` | Second-opinion evaluator | `llm.invoke` |
| `agent://fallback-evaluator` | Fallback evaluator | `llm.invoke` |
| `agent://schema-repair-agent` | Schema repair agent | *(none)* |
| `agent://prompt-proposer` | Prompt proposer | `llm.invoke` |
| `agent://calibration-evaluator` | Calibration evaluator | `llm.invoke` |
| `agent://meta-optimizer-grading` | Meta-optimizer (grading) | `firestore.read`, `firestore.write` |
| `agent://meta-optimizer-audit` | Meta-optimizer (audit) | `firestore.read`, `firestore.write` |

The schema repair agent holds **no** capability of its own on purpose: it is a
deterministic retry loop that re-invokes the caller's evaluator, so the call it
retries is authorised under the caller's principal, not under a principal of its
own. No agent principal holds `sis.write`.

### Infrastructure principals

| Principal | Responsibility | Capabilities |
|---|---|---|
| `pipeline-orchestrator` | Job records, checkpoints and stage state | `firestore.read`, `firestore.write` |
| `exam-fetcher` | Stages exam batch objects from the upload bucket | `gcs.read` |
| `sis-writer` | Writes grade records to the SIS and the Firestore ledger | `sis.write`, `firestore.write` |

## 3. Where enforcement happens

The gate is `core/harness/capabilities.py` (domain-agnostic mechanism) fed by
`core/fleet/` (the declarations). It follows the existing harness classifier —
**DENY > QUARANTINE > ALLOW** — and composes with the rules already in place, so
a SIS write must clear the capability rule *and* the manifest-scope rule *and*
the confidence rule.

| External action | Call site | Principal | Effect of a denial |
|---|---|---|---|
| GCS batch read | `stages_assessment.build_fetch_step` | `exam-fetcher` | Stage fails loudly; nothing is staged |
| Grading LLM call | `grade_guard.GradeGuard._guarded` | `grading-agent` | Submission is isolated and dead-lettered; the batch continues |
| Armor LLM call | `grade_guard.GradeGuard._screen_armor` | `armor-screener` | Raises: the grade stage **fails closed** rather than treating an unscreened page as clean |
| Curriculum audit LLM call | `stages_assessment.build_audit_step` | `curriculum-auditor` | Stage fails loudly |
| Firestore checkpoint write | `runner.JobRunner._process` | `pipeline-orchestrator` | Job aborts before any state is written |
| SIS write | `sync_governance.build_sis_permission_gate` | `sis-writer` | The record is not written and not silently quarantined; the denial is logged and recorded |

Two properties are worth stating explicitly:

- **Fail closed on unknown input.** A tool that maps to no declared capability
  is denied, and an agent id that is not in the registry is denied. Adding a new
  external action without declaring it therefore breaks loudly instead of
  inheriting ambient permission.
- **The check precedes the network call.** Every gate above runs before the
  client is invoked, so a violation costs zero tokens and produces no side
  effect.

## 4. Attribution: telemetry and provenance

- **Spans.** Grading and armor spans carry `agent.id` and `agent.principal`. A
  denial emits a `CapabilityDenied` span with `permission.decision`,
  `permission.target` and the reason.
- **Capability ledger.** `capability_scope()` collects a
  `CapabilityAuditRecord` per authorisation decision — allow and deny alike —
  for the duration of a job. The runner attaches the denials to the audit-trail
  summary (`capability_denials`), which lands in the Firestore audit collection
  in cloud mode and `.local_data/audit/<job>.jsonl` locally.
- **Provenance.** Every `SISGradeRecord` now carries `agent_id` (which agent
  produced the grade) and `writer_principal` (which principal wrote it),
  alongside the prompt-version and evidence hashes that were already there.

## 5. Service accounts to create (operator action)

**Nothing in this repository creates service accounts or edits IAM.** The code
path exists and is inert until an operator applies the following and sets the
settings in §6.

The recommendation is deliberately narrow. A separate GCP service account per
agent buys nothing while all agents share one Cloud Run process — they would all
be reachable from the same code, so the isolation would be cosmetic. It buys a
great deal for the one principal whose blast radius reaches outside the system:
the SIS writer.

### 5.1 The SIS writer (implement this one)

```bash
gcloud iam service-accounts create gradesync-sis-writer \
  --project=PROJECT_ID \
  --display-name="GradeSync SIS writer"

# Only what the writer needs: the SIS ledger collection and nothing else.
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member=serviceAccount:gradesync-sis-writer@PROJECT_ID.iam.gserviceaccount.com \
  --role=roles/datastore.user

# The runtime identity may mint tokens for the writer, and nothing more.
gcloud iam service-accounts add-iam-policy-binding \
  gradesync-sis-writer@PROJECT_ID.iam.gserviceaccount.com \
  --project=PROJECT_ID \
  --member=serviceAccount:autocurricula-runner@PROJECT_ID.iam.gserviceaccount.com \
  --role=roles/iam.serviceAccountTokenCreator
```

The runtime service account itself should then **lose** any direct write path to
the SIS ledger, so that the only way to reach it is through the impersonation
step, which is auditable in Cloud Audit Logs as a
`GenerateAccessToken`/`GenerateIdToken` call naming the writer.

### 5.2 The red-team campaign (when it is scheduled)

Block C of `self-learning-fleet.md` requires the campaign to run with **no SIS
access and no write access to production Firestore collections**. Today the
campaign is a local CLI (`scripts/run_red_team.py`) that touches neither, so no
service account is needed. If it is ever moved to a Cloud Run job, create
`gradesync-redteam` with `roles/aiplatform.user` and object access to a
dedicated `redteam/` bucket prefix only.

### 5.3 What is deliberately *not* split

`exam-fetcher`, `pipeline-orchestrator` and the model-calling agents keep the
ambient runtime identity. Splitting them would add IAM surface without adding
containment, because a compromise of the process reaches all of them regardless.
They are still separate *principals* with separate capability sets, which is
what makes the in-process denial meaningful.

## 6. Configuration

| Variable | Default | Effect |
|---|---|---|
| `GRADESYNC_RUNTIME_SERVICE_ACCOUNT` | *(empty)* | The ambient Cloud Run identity, reported in the registry. Empty reports `ambient:cloud-run-runtime-identity` |
| `GRADESYNC_SIS_WRITER_SERVICE_ACCOUNT` | *(empty)* | Dedicated SA for the SIS writer. Empty means no dedicated identity |
| `GRADESYNC_AGENT_IMPERSONATION_ENABLED` | `false` | Turns on IAM Service Account Credentials impersonation for principals that have a dedicated SA |
| `GRADESYNC_AGENT_IMPERSONATION_LIFETIME_SECONDS` | `3600` | Lifetime requested for the impersonated credential |
| `GRADESYNC_SIS_AUDIENCE` | *(empty)* | OIDC audience for the SIS ID token; falls back to `GRADESYNC_SIS_BASE_URL` |

`core/fleet/credentials.py` implements both credential shapes:

- **Firestore ledger path** — `sis_writer_firestore_client()` builds a Firestore
  client with impersonated credentials for the writer SA;
- **HTTP SIS path** — `sis_writer_authorization()` mints an OIDC **ID token**
  for the SIS audience via `IDTokenCredentials` on the writer SA and uses it as
  the bearer, instead of the static `GRADESYNC_SIS_API_TOKEN`.

Both **fall back to the ambient runtime identity** when impersonation is off or
when the IAM call fails, and the fallback is logged. That is a deliberate
availability choice: a token-minting outage must not stop grades reaching the
school, and the in-process capability gate still applies either way.

## 7. Honest limits

- **In-process, not cloud-enforced.** The capability gate is a control inside
  one Python process. It stops an agent that misbehaves — a prompt-injected
  grader trying to write another student's record, a stage wired to a tool it
  was never granted — and it produces an audit record when it does. It does not
  stop code that is modified to bypass it. Only cloud IAM does that, and only
  for the one principal that has a dedicated SA.
- **One dedicated SA, not eleven.** Until §5.1 is applied by an operator,
  `dedicated_service_accounts` in the registry is `0` and every principal
  reports the ambient identity. The registry reports this truthfully rather than
  claiming an identity that does not exist.
- **The gate covers declared actions.** Firestore reads and L2 vector search are
  not individually gated today; they are covered by the principal's declared
  capability set but not by a call-site check. The four action classes that are
  checked at the call site are the ones listed in §3.
- **Impersonation is untested against live IAM.** The credential path is
  exercised by unit tests with the IAM call stubbed and by its fallback
  behaviour; it has not been run against a real dedicated service account,
  because creating one is an operator action outside this repository.
