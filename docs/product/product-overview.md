# The GradeSync Engine as a Product

| | |
|---|---|
| **Status** | Maintained — living document, updated with every implementation cycle |
| **Audience** | School leadership, IT administrators, evaluators, integration partners |
| **Last updated** | 2026-08-17 (Implementation 004 — agent harness) |
| **Related** | [How It Works](how-it-works.md) · [Root README](../../README.md) |

---

## Table of contents

1. [Elevator pitch](#1-elevator-pitch)
2. [Who it is for](#2-who-it-is-for)
3. [What goes in](#3-what-goes-in)
4. [What comes out](#4-what-comes-out)
5. [Fundamental guarantees](#5-fundamental-guarantees)
6. [Return on investment](#6-return-on-investment)
7. [A day in the life](#7-a-day-in-the-life)
8. [Deployment modes](#8-deployment-modes)
9. [Honest limits](#9-honest-limits)
10. [Roadmap](#10-roadmap)

---

## 1. Elevator pitch

In goes a batch of scanned exams; out come audited grades in the SIS, curriculum
coverage maps, and early dropout alerts. Teachers don't "use" an app or learn an
interface: they drop files in a bucket and get their evenings back. It is pure
backoffice infrastructure — no chat, nothing to learn.

Behind that simplicity sits a verifiable machine: every grade cites page-level
evidence from the student's own manuscript, every low-confidence result is
escalated to a human instead of guessed, and the engine improves itself against
human-graded samples under an anti-cheating guardrail that it cannot bypass.

## 2. Who it is for

| Persona | What they get |
|---|---|
| **Teacher** | Grading hours back; drafts with cited evidence; a 10-minute exception queue instead of 12 weekly hours of marking |
| **Academic coordinator** | Curriculum coverage maps per assessment; explainable dropout risk; control over rubrics and standards (once per term) |
| **School IT** | A Cloud Run service with health endpoints, idempotent ingestion, checkpoints, and one SIS connector to configure |
| **Families / auditors** | Defensible evaluation: every automated decision has a versioned prompt, cited evidence, and a timestamped record |

## 3. What goes in

| Input | Source | Frequency |
|---|---|---|
| Scanned exam batch (handwritten PDFs/images) | Teacher or front office | Per assessment |
| Batch metadata (subject, grade, active rubric) | **Auto-inferred from the path/lot-code convention** or explicit `batch.json` | Automatic per event |
| Rubrics + national curriculum standard | Pedagogical coordination (`catalog-defaults.json`) | Once per term |
| Calibration samples (human ground truth) | Validated historical assessments | Periodic — feeds self-improvement |
| SIS/LMS credentials & connectors | IT / administration | One-time setup |

The only daily human action is **uploading files**. Everything else is one-time or
per-term configuration.

## 4. What comes out

**For the teacher**

- Criterion-level grades with cited evidence (page + verbatim quote), not opaque numbers
- Written feedback per submission
- Minutes of turnaround instead of days

**For academic coordination**

- Automatic curriculum reconciliation: ministry competencies covered vs. orphaned
- Early dropout alerts: student, risk level, *why* (mathematical drivers), suggested interventions
- Class mastery map per competency — direct input for planning the next lesson

**For the SIS / backoffice**

- Grade records already written, with competency codes — zero transcription, zero typos

**For the institution's own records**

- Per-job verification reports (goal checks, rework attempts, pending approvals vs. unresolved)
- Optimizer reports: active prompt version, agreement with humans (MAE/QWK/bias), rejected mutations and why
- Complete audit trail: every decision traceable to a prompt version, evidence span, and timestamp

## 5. Fundamental guarantees

1. **Transactional idempotency** — even if Pub/Sub delivers the message multiple
   times, an exam is never duplicated or computed twice in the SIS.
2. **Absolute defensibility** — every grade carries an `EvidenceSpan` with a
   verbatim quote and page number; a parent complaint is answered with evidence
   from the student's own manuscript.
3. **Confidence-threshold escalation** — ambiguous answers or illegible handwriting
   are never guessed: they go to quarantine with the exact page and cited excerpt
   pre-highlighted for one-click teacher approval. The engine may *re-try* with a
   second opinion and update the proposal, but a human still clicks.
4. **Deterministic, explainable risk** — early-warning alerts come from math
   (z-scores, longitudinal slopes over persistent history), not free-form LLM
   opinion.
5. **Anti-gaming self-improvement** — the prompt optimizer only promotes variants
   that improve human agreement **and** clear the composite production gate
   (`QWK ≥ 0.85 ∧ MAE ≤ 0.4 ∧ |Bias| < 0.1`); variance collapse, constant outputs,
   and metric gaming without ground-truth contact are structurally blocked.
6. **Long-running fault tolerance** — persistent per-stage checkpoints; if
   infrastructure is interrupted, the pipeline resumes exactly at the pending stage
   without recomputing prior work. A failing exam is isolated (blast-radius
   containment) instead of failing the batch.
7. **Provenance ledger** — every grade written to the SIS carries a cryptographic
   receipt: the SHA-256 of the exact prompt version used and of each cited evidence
   fragment. Audits reconstruct *which* agent version and *which* manuscript excerpt
   produced every score.
8. **Batch circuit breaker** — if an unusual share of a batch (>15%) requires human
   review, automatic sync for the whole batch is suspended: the system assumes a
   defective scan, a wrong rubric, or model drift rather than pushing questionable
   grades, and escalates everything to review.

## 6. Return on investment

- **Teacher time**: from ~12 weekly hours of manual grading to zero transcription
  and ~10 minutes of exception review per assessment.
- **Time-to-feedback**: from a typical 14-day grading cycle to **under 10 minutes**
  after the scan lands in the bucket.
- **Data quality**: competency-coded grades written directly to the SIS, with
  per-criterion mastery maps generated as a by-product.
- **Dropout prevention**: longitudinal risk signals surface students in decline
  terms before humans would notice.

(These are design targets based on the automated pipeline; measure them against
your own baseline in the first term.)

## 7. A day in the life

1. **08:02** — Front office uploads 30 scanned exams to
   `batches/2026_Matematicas_10A_Parcial1/`.
2. **08:02** — Pub/Sub pushes the event; the webhook acknowledges in milliseconds.
3. **08:04** — Grades, curriculum audit, and risk assessments are done; 27 records
   auto-sync to the SIS; 3 illegible answers land in the review queue with pages
   and quotes pre-highlighted.
4. **08:04** — The verifier re-tries those 3 with a second opinion; 2 clear the
   confidence gate and their review items are updated (still awaiting one click).
5. **08:15** — The teacher opens `GET /review/pending`, approves 2 items with one
   click each, and escalates the remaining one — 10 minutes, with the manuscript
   excerpt already on screen.
6. **Nightly / per-trigger** — the optimizers run calibration tournaments and
   promote a new prompt version only if it demonstrably agrees better with the
   school's own human graders.

## 8. Deployment modes

- **Local mode** (`GRADESYNC_LOCAL_MODE=true`, the default without a GCP project):
  the entire pipeline runs offline — local staging directory, TF-IDF retrieval,
  JSON stores, JSONL SIS log. Ideal for pilots, evaluation, and CI.
- **GCP production**: Cloud Run (`min-instances=1`, 900s timeout), Pub/Sub push
  with token verification, Firestore (checkpoints, profiles, vector search,
  prompts, reviews), Vertex AI (Gemini 3.5 Pro/Flash, text embeddings), SIS over
  HTTPS. Deploy via the included `cloudbuild.yaml`.

## 9. Honest limits

- Output quality is a function of input quality: a vague rubric produces
  well-executed grading against a vague rubric.
- The self-improvement loop **requires** human ground truth; without calibration
  samples the engine grades but does not learn.
- Genuinely ambiguous material (smudged pages, missing sheets) fails explicitly
  and is escalated — the product never invents a reading.
- Second-opinion rework is a GCP-mode capability; in local mode verification runs
  the same goal checks but cannot re-grade.
- ROI figures are design targets; validate against your baseline.

## 10. Roadmap

- QR/OCR pre-printed cover pages as a third manifest mode (same seam as path
  convention and `batch.json`)
- Shadow rollout of accepted prompt variants against live traffic with automatic
  rollback on drift
- Dedicated nightly optimizer schedule (independent of job traffic)
- Per-criterion production drift monitoring (beyond calibration sets)
- Planner-based per-job workflows (currently a deliberate fixed, auditable DAG)
