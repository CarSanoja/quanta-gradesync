# The GradeSync Engine as a Product

| | |
|---|---|
| **Status** | Maintained — living document, updated with every implementation cycle |
| **Audience** | School leadership, IT administrators, evaluators, integration partners |
| **Last updated** | 2026-08-20 (the two surfaces, accessibility, and the self-learning roadmap) |
| **Related** | [How It Works](how-it-works.md) · [Root README](../../README.md) · [Adversarial review of limits](../architecture/limits-adversarial-review.md) · [Self-learning fleet](../architecture/self-learning-fleet.md) |

---

## Table of contents

1. [Elevator pitch](#1-elevator-pitch)
2. [Who it is for](#2-who-it-is-for)
   - [2.1 The two surfaces](#21-the-two-surfaces)
   - [2.2 What each persona sees, touches, and never sees](#22-what-each-persona-sees-touches-and-never-sees)
   - [2.3 Designing for Beatriz: 150 exams, one afternoon](#23-designing-for-beatriz-150-exams-one-afternoon)
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

### 2.1 The two surfaces

The engine is background infrastructure, but two groups of people do occasionally
need to look at it, and they need to see completely different things. There are
exactly two surfaces, sharing one API:

| | `GET /teacher` | `GET /console` |
|---|---|---|
| **For** | Teachers | School IT and operations |
| **Language** | Plain words. No pipeline vocabulary, no job ids, no stage names | Operational vocabulary: jobs, stages, quarantine ratio, dead letters, spans |
| **The main question it answers** | "What still needs me, and how long will it take?" | "Is the service healthy, and where is this batch?" |
| **Core views** | Exams waiting for your review · Upload scans · Recently synced grades | Jobs timeline · Review queue · Ingest · SIS ledger · Live trace · Optimizer report |
| **Review model** | Guided one-by-one: page image, the quoted excerpt, the reason in a sentence, one decision | The same queue with the operational detail attached: reasons, evidence spans, document URI, proposed record |
| **Access** | One access code, entered once, stored on the device | The same shared token; intended for staff who already administer the service |

**What the teacher surface does that the console does not.**

- **Naming happens in the browser, never on disk.** Files are picked as they
  are; each one gets a name box. `ana-torres.pdf` is pre-filled as *Ana Torres*;
  `IMG_2831.jpg` simply waits for a name and does not hold up the rest of the
  batch. Nothing on the teacher's computer is ever renamed.
- **Collisions ask instead of guessing.** A name that already has a scan
  produces a question with two honest answers: replace the scan (the exam is
  re-graded, the previous scan is kept) or save it as a different student.
- **Pages of one exam are recognised.** `ana-p1.jpg` and `ana-p2.jpg` prompt a
  choice — combine into one PDF, or upload as separate students — instead of
  silently creating two half-graded students.
- **Guided review.** A "review one by one" mode walks the queue with progress,
  so a teacher never has to decide which card to open next.
- **Scale is visible.** Large uploads show a progress bar, per-file chips, a
  "retry the ones that failed" action, and a collapse after eight files so the
  page stays readable at 150 files.

**What the console does that the teacher surface does not.** Job stages and
timings, the live trace of a running batch, the SIS ledger as raw records, the
dead-letter queue, and the optimizer report. None of this appears on the teacher
surface, by design: a teacher who sees a stage diagram has been given a problem,
not a tool.

### 2.2 What each persona sees, touches, and never sees

| Persona | Sees | Touches | Never sees |
|---|---|---|---|
| **Teacher** | Her queue in plain words; the scanned page with the cited excerpt; recently synced grades for her classes | Uploads scans; approves, dismisses (and, on the roadmap, corrects) one exam at a time | Job ids, stage names, confidence numbers, prompt versions, other teachers' classes, anything about the model |
| **Academic coordinator** | Curriculum coverage per assessment; class mastery per competency; risk alerts with their mathematical drivers | Rubrics and the curriculum binding, once per term | Individual model calls, infrastructure state, the review queue of any single teacher |
| **School IT** | Service health, jobs and stages, quarantine volume, SIS ledger, dead letters, live traces | Deployment, credentials, the SIS connector, thresholds | Student work as pedagogy — IT sees pages only when diagnosing an ingestion fault |
| **Families / auditors** | On request: the grade, the cited excerpt from the student's own manuscript, the timestamp, and which prompt version produced it | Nothing — this is a read path | Other students' data; the engine's internals |

### 2.3 Designing for Beatriz: 150 exams, one afternoon

Beatriz teaches mathematics to five classes — around 150 students. She scans at
the front office, photographs the leftovers with her phone on the way home, and
works on a school connection that drops. She is the person the product is for,
and she is the reason the following are product requirements rather than nice
touches:

| Requirement | Why it matters to her |
|---|---|
| **Naming in the browser** | She will not rename 150 files on a shared office computer, and she should not have to |
| **One file per student, pages combined** | A five-page exam is one student, and the surface has to say so before the upload, not after the grades |
| **Nothing blocks on one bad file** | An unnamed phone photo holds up itself and nothing else |
| **Resumable, retryable uploads** | Her connection drops. Retry must never create a second copy of a student |
| **A queue that ends** | The review section states how many are left and shows a finished state, so ten minutes feels like ten minutes |
| **Readable at 200 % zoom, usable by keyboard** | She reviews on a laptop with the display scaled up, late, and sometimes with a trackpad she dislikes. Every control is reachable by keyboard, focus is visible, status is never conveyed by colour alone, and the reduced-motion preference is honoured |
| **The page image is the evidence** | She decides by reading the manuscript, not by trusting a number. The excerpt is quoted and the page is on screen |
| **Plain language for every reason** | "The scan is too blurred to read with confidence" — never "effective confidence 0.490 below threshold 0.85" |

Two of Beatriz's requirements are **not met today** and are tracked in
[§9 Honest limits](#9-honest-limits): a batch is currently capped at 40 files, and
a very large upload spread over several minutes can start grading before all the
files have arrived. Both are first in the roadmap below.

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

**Limits found by our own adversarial review (2026-08-20).** A full engineering
audit of the shipped code and every measured run is published at
[`docs/architecture/limits-adversarial-review.md`](../architecture/limits-adversarial-review.md).
The items a school should know about before a term that counts:

- **Batch size is capped at 40 files.** A 150-exam afternoon has to be split into
  four uploads today. Raising this cap is the first roadmap item.
- **A very large upload can start early.** If files arrive slowly enough, the
  engine can begin grading what it has and treat later files as a repeat of the
  same batch. Until the fix ships, upload a batch in one go and confirm the
  received count matches what you sent.
- **How much the engine agrees with your teachers is not yet established.** The
  agreement figures published so far come from **four** human-graded exams. That
  is enough to prove the machinery runs; it is not enough to state an accuracy.
  Roughly 30–50 human-graded exams are needed before the agreement target means
  anything, and the engine's own promotion gate should refuse to promote below
  that number.
- **Evidence quotes are not yet mechanically checked in cloud runs.** Every grade
  cites a verbatim excerpt, and those excerpts have been verified by hand in our
  test runs — but the automatic check that compares a quote against the page has
  no page transcript to work with in cloud mode. Until the transcript step ships,
  treat the citation as a strong aid to review, not as a machine-verified fact.
- **Confidence does not yet vary much.** The model reports high confidence on
  almost everything, so escalation is currently driven by the deterministic
  scan-legibility check rather than by the model's own uncertainty. A page that is
  sharp but ambiguous may not escalate.
- **One tested attack.** Handwritten prompt injection is caught in production, and
  the caught example is real — but the test set is a single attack pattern. The
  breadth of the defence is unmeasured, and a systematic adversarial campaign is
  on the roadmap.
- **All test handwriting is synthetic.** Every accuracy figure to date comes from
  fabricated scans. Real student handwriting has not yet been graded at scale.
- **Dropout alerts need history.** The early-warning mathematics needs several
  terms of data before its higher severity levels can trigger at all, and its
  thresholds have not been validated against a cohort with known outcomes. Treat
  the first year's alerts as informational.
- **A student's term history can be overwritten.** If two assessments for the same
  class are processed in the same calendar month, the later one currently replaces
  the earlier one in the student's history. Coverage maps and grades in the SIS are
  unaffected; the longitudinal profile is.
- **Corrections are approve-or-drop.** A teacher can approve a proposed grade or
  set it aside, but cannot yet type a corrected score in the surface — and when she
  sets one aside, the engine learns nothing from it. This is the single biggest
  missed opportunity in the product today, and the roadmap's second item.
- **An exam that crashes the grader disappears quietly.** It produces no grade and
  no review card. Until the completeness ledger ships, reconcile the count of
  synced plus quarantined records against the number of files you uploaded.
- **The surfaces require credentials.** Organisation policy prevents anonymous
  access, so `/teacher` and `/console` are reachable only by authorised users.

## 10. Roadmap

The engineering design behind these items is
[`docs/architecture/self-learning-fleet.md`](../architecture/self-learning-fleet.md);
what follows is what a school gets, not how it is built.

### This term — closing the gaps a school would feel

| What the school gets | Today |
|---|---|
| **Upload a whole day's exams in one go.** The 40-file cap is lifted and very large uploads are held until every file has arrived, so nothing starts half-graded | Batches are capped, and a slow upload can begin early |
| **Every exam accounted for.** The batch report becomes a complete list: graded, waiting for you, or failed — with a card for the failures too. The count always matches what you uploaded | An exam that crashes the grader produces no grade and no card |
| **Type the right grade.** When a teacher disagrees with a proposal, she corrects it in the surface instead of approving something she does not believe | Approve or set aside, nothing else |
| **Citations checked by machine.** Each cited excerpt is verified against a transcript of the page before the grade is allowed to sync — and confidence becomes "how much of this grade is backed by text we actually found", instead of the model's opinion of itself | The citation is shown but not mechanically verified in cloud runs |
| **Escalation you can tune.** Because confidence is derived from evidence rather than self-reported, the school can move the escalation dial and see the quarantine volume respond | The dial has little effect |
| **A security control that fails safely.** If the injection screen cannot run, the exam waits for a human instead of passing | A failed screen currently reads as "clean" |

### Next term — the engine that corrects itself

| What the school gets | Why it matters |
|---|---|
| **Every click teaches the engine.** Approvals, dismissals and corrections become the school's own calibration set — so agreement is measured against *your* teachers on *your* handwriting, and it grows every week at no extra cost | Today the engine learns from four exams and nothing a teacher does feeds back |
| **Beliefs that expire.** What the engine believes about a student, a class or a rubric carries the evidence behind it and loses confidence unless it is re-confirmed. A nightly review re-examines a sample and demotes what no longer holds | Today a stored belief is permanent and unexamined |
| **A profile that repairs itself.** If a term was graded badly, the affected assessments are re-queued, teachers correct them, and every dependent number — term average, class mastery map, risk history — is recomputed from the corrected facts. Nothing is destroyed; corrections are recorded, not overwritten | Today a bad term contaminates a student's history permanently |
| **A standing adversary.** A red-team routine invents new ways to cheat the grader every night and reports the catch rate — and, more importantly, whether any attack actually moved a grade | Today the defence is proven against one attack |
| **A second, independent reader.** Arithmetic and algebra are re-checked by a deterministic checker with no model in it; where the two readers disagree on a high-stakes grade, a human decides before anything is written | Today one model family reads, screens and re-checks its own work |
| **Drift alarms between terms.** A frozen reference set is re-graded on a schedule, so the school is told the difference between "the class is weaker this term" and "the grader changed" | Today neither is detectable |
| **Honest promotion.** A new prompt version is promoted only when it beats the current one on exams it has never seen, with the statistical margin published — and the engine refuses to promote at all on too few samples | Today selection and evaluation share the same four exams |

### Longer term

- QR/OCR pre-printed cover pages as a third manifest mode (same seam as path
  convention and `batch.json`)
- Shadow rollout of accepted prompt variants against live traffic with automatic
  rollback on drift
- Per-criterion production drift monitoring across cohorts, not only against
  calibration sets
- Validation of the dropout early-warning thresholds against real cohorts with
  known outcomes, before any alert is used for intervention decisions
- Planner-based per-job workflows (currently a deliberate fixed, auditable DAG)
- A published quality report per term: agreement with your teachers, escalation
  precision, attack catch rate, and every number's confidence interval
  (specification: [`docs/benchmarks/gradesync-bench.md`](../benchmarks/gradesync-bench.md))
