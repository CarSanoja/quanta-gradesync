# The self-learning fleet — architecture for an engine that corrects itself

| | |
|---|---|
| **Status** | Design document — proposed architecture, not shipped behaviour |
| **Audience** | Engineers implementing the next two cycles; reviewers checking the design against the measured limits |
| **Date** | 2026-08-20 |
| **Premise** | Every block here exists to close a numbered finding in the [adversarial review](limits-adversarial-review.md). A block with no finding behind it is not in this document |
| **Related** | [Adversarial review](limits-adversarial-review.md) · [GradeSync-Bench](../benchmarks/gradesync-bench.md) · [How it works](../product/how-it-works.md) |

---

## 0. What the platform has already proved, and what that buys

Everything below is budgeted against numbers the system actually produced, so
that no block is proposed on a hope about cost or latency.

| Measured fact | Source | What it licenses |
|---|---|---|
| 8-exam batch: 43.9 s wall clock, $0.31275, 16 LLM calls | [e2e-2026-08-19](../reports/e2e-2026-08-19.md) | A per-exam budget of **$0.0391 and 5.0 s** to reason against |
| Grade stage 28.1 s for 8 concurrent exams; per-exam spans 16–26 s | e2e-2026-08-19 | Fan-out is real: adding a *concurrent* stage costs ≈ its own single-call latency, not N × it |
| Audit stage: 8 Flash-Lite calls, 13 744 in / 1 787 out, $0.00859, 3.2 s | e2e-2026-08-19 | A per-page Flash-Lite pass over an image costs ≈ **$0.001 and ≈ 3 s wall clock at batch concurrency** |
| Rework: 14 Flash-Lite grading calls, 54 716 input tokens, $0.0366 | e2e-2026-08-19 | Second-opinion grading is ~6 % of the cost of primary grading |
| Calibration loop: 19 calls, 124.9 s, $0.6296 | [calibration-2026-08-20](../reports/calibration-2026-08-20.md) | A full tournament over 4 exams is ~$0.63; over 60 exams it is ~15× that, which is the real constraint |
| Stages checkpoint and resume; deliveries 2 and 3 of a resumed job cost 2.3 s and 8.0 s | [resilience-2026-08-20](../reports/resilience-2026-08-20.md) | New stages can be added to the DAG without re-running paid work on retry |
| Firestore vector search works end to end once the index exists, and degrades to empty context on API error | e2e-2026-08-19 (bugs 3 and 4) | L2 retrieval is available for claim lookup, with a known failure mode |
| Scale-to-zero, event-driven, `min-instances=0` | [deploy-2026-08-19](../reports/deploy-2026-08-19.md) | Background/scheduled work is free when idle |

**All costs and latencies stated for the new blocks are targets derived from
these measurements, not measurements.** They are labelled *(target)*.

---

## 1. The shape of the change

Today there are two planes. The hot plane grades; the cold plane was supposed to
improve prompts and in production has never run (finding F-12).

```text
  HOT PLANE   fetch → grade → audit → risk → sync → verify → optimize
  COLD PLANE  calibration tournament (manual, N=4, in-sample)
```

The proposal adds a third plane and rewires the first two around a single idea:
**nothing the system believes is permanent, and every human touch is a label.**

```text
  ┌── HOT PLANE (per job, seconds) ───────────────────────────────────────────┐
  │ fetch → transcribe → grade → audit → dissent → risk → sync → verify        │
  │            (D)                        (E)                                  │
  │                     ▲ evidence-coverage confidence (D) replaces self-report │
  └───────────────┬────────────────────────────────────────────────────────────┘
                  │ every decision, every human click
                  ▼
  ┌── REFLECTIVE PLANE (scheduled, minutes/night) ────────────────────────────┐
  │  Claim ledger (A)  ←→  Challenge runner (A)  ←→  Label pool (B)            │
  │  Red-team campaign (C)      Drift sentinels (F)      Completeness audit (H) │
  └───────────────┬────────────────────────────────────────────────────────────┘
                  │ labels, catch rates, drift alarms, demoted claims
                  ▼
  ┌── COLD PLANE (per trigger, held-out) ─────────────────────────────────────┐
  │  train / dev / test split (G) → tournament → gate on the LOWER CI bound    │
  │  shadow replay on model-version change (I)                                 │
  └───────────────────────────────────────────────────────────────────────────┘
```

Block index:

| Block | Name | Closes |
|---|---|---|
| **A** | Contending memories — claims with decay and scheduled challenges | F-17 – F-22, F-19, F-20 |
| **B** | The review queue as a free active-learning signal | F-21, F-22, F-09 |
| **C** | Adversarial self-play — a scheduled red team | F-13, F-14, F-15, F-02 |
| **D** | Evidence-coverage confidence — mechanically verified quotes | F-01, F-04, F-05 |
| **E** | Cross-model dissent — a structurally different checker | F-15, F-30 |
| **F** | Drift sentinels between cohorts and terms | F-30, F-33 |
| **G** | Label economy and holdout discipline | F-08, F-09, F-10, F-11 |
| **H** | Completeness ledger — no exam disappears | F-16, F-27, F-28, F-29 |
| **I** | Version pinning and shadow replay | F-30, F-33 |

---

## 2. Block A — Contending memories

> Today an L3 entry is a fact written once by whoever ran last. After this block
> it is a **claim** with evidence on both sides, a confidence that decays, and a
> scheduled adversary whose job is to knock it down.

### A.1 Mechanism

Every durable belief becomes a `Claim` document. Nothing writes a bare value
into a profile any more; writers assert claims, and readers project claims into
values.

| Field | Type | Purpose |
|---|---|---|
| `claim_id` | string | `{scope}:{subject_key}:{predicate}` — e.g. `student:ana-torres:term_mastery:2026-T2` |
| `scope` | enum | `student` · `class` · `rubric` · `prompt` · `armor` · `operational` |
| `predicate` / `value` | string / typed | What is claimed (`term_mastery = 0.82`, `criterion_ambiguous = true`) |
| `support[]` | list of `EvidenceRef` | Everything that argues for it |
| `refutations[]` | list of `EvidenceRef` | Everything that argues against it |
| `confidence` | float | Derived, never written by a model (§A.3) |
| `asserted_by` / `asserted_at` | string / ts | Provenance of the assertion |
| `last_confirmed_at` | ts | Resets the decay clock |
| `half_life_days` | float | Per-scope (§A.3) |
| `status` | enum | `active` · `contested` · `dormant` · `retracted` · `superseded` |
| `supersedes` / `superseded_by` | claim_id | Lineage, so history is never destroyed |

`EvidenceRef` carries `kind`, `weight`, `uri` (a `gs://` page, a review id, a job
id, a bench run id), `observed_at`, and a SHA-256 of the referenced artefact so
the link is verifiable later — reusing the provenance machinery that already
exists in `core/harness/provenance.py`.

**Evidence weights (the currency of the protocol).** These are the only numbers
that decide a dispute:

| Evidence kind | Weight | Rationale |
|---|---:|---|
| Human **override** with a corrected score | 1.00 | A domain expert looked at the page and disagreed on the record |
| Human **approve** of a quarantined item | 0.60 | Agreement, but under an approval bias (one click vs. re-grading) |
| Human **dismiss** with a captured reason | 0.60 | Explicit rejection; today discarded entirely (F-22) |
| Independent checker agreement (Block E) | 0.40 | Structurally different reader reached the same reading |
| Verified-evidence grading (coverage ≥ 0.8, Block D) | 0.25 | Machine reading with mechanically checked quotes |
| Unverified grading result | 0.10 | What the system currently treats as fact |
| Model self-reported confidence | **0.00** | Measured to be constant at 0.95–1.00 (F-01); it is not evidence |

### A.2 Data flow

```text
sync / review / bench / red-team
        │  assert(claim, evidence)
        ▼
   Firestore `claims`  ──(read projection)──►  risk detector, grading context,
        │                                       teacher surface, class maps
        │  nightly sample
        ▼
   Challenge runner (Cloud Run job, Cloud Scheduler)
        │  for each sampled claim:
        │    1. recompute the deterministic projection from raw facts
        │    2. search `assessment_facts` + `labels` for contradicting evidence
        │    3. (optional) one Flash-Lite call for semantic contradiction only
        ▼
   verdict: confirm (reset clock) · weaken · contest · retract
        │  contested claims with value-at-risk above τ
        ▼
   Review queue as a `memory_dispute` item → human decides → weight 1.00 evidence
```

### A.3 The reconciliation protocol, precisely

**Confidence is derived, not asserted.**

```text
raw      = Σ weight(support) − Σ weight(refutations)
base     = clamp(raw / (raw + 1), 0, 1)              # saturating, so volume ≠ certainty
decayed  = base × 0.5 ^ (days_since_last_confirmed / half_life_days)
confidence = max(decayed, 0.02)
```

| Scope | `half_life_days` | Reasoning |
|---|---:|---|
| `student` (mastery, risk) | 120 | One term. A belief about a child must be re-earned every term |
| `class` (competency coverage) | 180 | Coverage moves with the syllabus |
| `rubric` (criterion semantics, ambiguity flags) | 365 | Stable within a school year |
| `prompt` (a variant's measured agreement) | 60 | Tied to a model version that can change under an alias (F-30) |
| `armor` (an attack class is caught) | 30 | The most adversarial scope decays fastest |

**Status transitions.**

| Transition | Trigger |
|---|---|
| `active → contested` | Any refutation with weight ≥ 0.60, or a challenge verdict of `contest` |
| `active → dormant` | `confidence < 0.30`. A dormant claim is still readable but is **excluded from grading context and from risk inputs** |
| `contested → active` | Confirming evidence restores the balance and resets `last_confirmed_at` |
| `contested → retracted` | Refutation weight exceeds support weight, or a human decides against it |
| `* → superseded` | A new claim with the same `claim_id` root and a higher-weight evidence base is asserted; the old one keeps its lineage |

Nothing is ever deleted. Retraction is a status plus a `superseded_by` pointer,
so an audit two years later can reconstruct what the system believed on any day.

**Who may challenge.**

| Challenger | Cadence | Scope it may challenge |
|---|---|---|
| Challenge runner (scheduled) | nightly | Any claim; samples by value-at-risk = `confidence × blast_radius` |
| Any human decision | immediate | The claims cited in the review item it decided |
| Drift sentinel (Block F) | weekly | `prompt` and `rubric` claims |
| Red-team campaign (Block C) | nightly | `armor` claims only |
| Completeness audit (Block H) | hourly | `operational` claims |

**What counts as evidence.** Only the table in §A.1. Explicitly *not* evidence:
a model's self-reported confidence; the fact that a claim has been read many
times; the age of a claim; agreement between two calls to the same model family
(that is one witness, not two — F-15).

**How conflicts resolve.** In order, stopping at the first that decides:

1. **Weight.** Higher total evidence weight wins.
2. **Recency at equal weight.** The more recent evidence wins; the loser becomes
   `superseded`, not deleted.
3. **Independence tie-break.** Evidence from structurally different sources
   (human + deterministic checker) beats a larger pile from one source.
4. **Escalation.** If 1–3 do not decide and `value_at_risk ≥ τ_escalate`, a
   `memory_dispute` review item is created with both sides rendered side by side.
   A human decision enters as weight 1.00 — and is itself a claim that decays.

**How a student profile self-corrects after a bad term of grading.** This is the
concrete scenario the block exists for: a model version shifted in March
(F-30/F-33), a whole cohort's word-problem scores drifted down half a point, and
nobody noticed until May.

1. **Facts are separated from aggregates.** A new append-only
   `assessment_facts` collection holds one immutable document per graded
   submission (`student_id`, `assessment_id`, `term_label`, per-criterion scores,
   evidence coverage, job id, prompt sha, model id, `retracted_at`). Term
   aggregates stop being written (killing F-18) and become a **projection**
   computed from non-retracted facts on read.
2. **The drift sentinel raises a refutation.** It asserts
   `refutes(class:10A:term_mastery:2026-T1, kind=drift_alarm, weight=0.5)` and
   attaches the affected `assessment_facts` ids.
3. **Sampling repairs the truth.** The affected facts are re-queued into the
   review queue as `regrade_requested` items, prioritised by
   `|Δ| × students_affected`. Teachers override the ones that are wrong; each
   override is a weight-1.00 label (Block B) **and** a retraction of the original
   fact.
4. **Projection recomputes.** Because aggregates are derived, retracting 40 facts
   and inserting 40 corrected ones repairs every dependent value — term average,
   class mastery map, z-score series — in one recompute, with no destructive
   write anywhere.
5. **Dependent claims re-derive.** Any `student:*:risk_level` claim whose support
   included a retracted fact drops below `τ_dormant` automatically (its support
   weight fell) and is re-asserted from the corrected projection on the next
   challenge pass. Guardian-facing alerts raised from retracted facts are marked
   `withdrawn`, with the date and the reason.

### A.4 GCP mapping

| Component | GCP primitive | Notes |
|---|---|---|
| Claim ledger | Firestore collections `claims`, `claim_evidence`, `assessment_facts` | Same client and auth as today's `profiles` |
| Claim retrieval by meaning | Firestore vector search on `claims.embedding` | The 768-d flat index pattern already proved out in e2e-2026-08-19 (bug 3/4) |
| Challenge runner | Cloud Run **job** + Cloud Scheduler (nightly 02:00 school time) | Separate from the request-serving service; scale-to-zero when idle |
| Dispute escalation | Existing `reviews` collection, new `item_kind` | Reuses the whole review surface for free |
| Withdrawal notices | Existing audit collection | Append-only, already in place |

### A.5 Budget *(target)*

| Item | Volume/night | Cost | Latency |
|---|---|---|---|
| Deterministic re-projection of sampled claims | 500 claims | Firestore reads only, < $0.01 | < 30 s |
| Semantic contradiction check (Flash-Lite, only for claims with text predicates) | ≤ 200 calls, ~1 k in / 200 out | ≈ $0.16 | ≈ 60 s at concurrency 20 |
| Escalations created | ≤ 10 | $0 | — |
| **Nightly total** | | **< $0.20** | **< 3 min** |

Reference points: the audit stage bills $0.00859 for 8 Flash-Lite calls with
images; text-only claim checks are cheaper per call than that.

### A.6 Failure containment

- The challenge runner is **read-mostly**: it may only change `status`,
  `confidence`, `last_confirmed_at`, and append evidence. It cannot write a
  score, cannot write to the SIS, and has no SIS credentials.
- A runner crash leaves claims untouched; confidence simply keeps decaying,
  which fails toward *less* trust.
- A runaway challenger is bounded by a per-night claim quota and by the same
  `ItemBudget` pattern already in `core/harness/budgets.py`.
- If the ledger is unreachable, readers fall back to the last projection cached
  in the job checkpoint and the job records `claims_unavailable` — the same
  degrade-to-empty-context pattern `FirestoreVectorMemory.query` already uses.

### A.7 The question it answers

> *When the engine was wrong about a student for a whole term, how long does it
> take the system to notice, and what does it cost to repair every downstream
> number?*

Target: detection within one challenge cycle of the first contradicting human
decision; full repair by recompute, with zero destructive writes.

---

## 3. Block B — The review queue as a free active-learning signal

> The system has graded dozens of exams in production and has **4** calibration
> samples. Every click a teacher makes is a label being thrown away (F-21, F-22).

### B.1 Mechanism

Three changes, in order of value:

1. **Add an override.** `POST /review/{id}/override` accepts corrected
   per-criterion scores, an optional reason code, and free text. It writes the
   corrected record to the SIS, retracts the machine fact, inserts a corrected
   fact, and emits a **weight-1.00 label**. Today a teacher who disagrees can
   only approve a number she believes is wrong or drop the exam.
2. **Make every decision a label.** Approve, dismiss and override all write a
   `Label` document: `submission_id`, `criterion_id`, `machine_score`,
   `human_score` (= machine score for approve, null for dismiss),
   `reviewer_id`, `decision_ms` (how long the card was open), `reason_code`,
   `page_uri`, `prompt_sha`, `model_id`, `evidence_coverage`.
3. **Sample deliberately.** A small share of *auto-synced* records — never
   quarantined ones — is routed to review as `audit_sample` items, so the label
   pool is not conditioned entirely on "the system already doubted this".
   Without this the pool is a biased sample of the system's own uncertainty and
   cannot estimate production accuracy.

**Sampling policy** (deterministic, seeded by job id so it is reproducible):

| Stratum | Share of auto-synced records | Why |
|---|---:|---|
| Uncertainty band (evidence coverage in the middle quintile) | 5 % | Classic active learning: labels where the model is least decided |
| Boundary band (score within ±0.25 of a rubric bucket edge) | 3 % | Where a half point changes a mastery bucket (F-11) |
| Random control | 2 % | Unbiased estimate of production accuracy |
| Disagreement (Block E flagged dissent but below the gate) | 100 % | Cheapest possible high-information label |

At 10 % overhead on a 30-exam assessment that is 3 extra cards. The teacher UI
must label them honestly — *"a spot check, the grade is already in the
gradebook"* — so a spot check is never mistaken for a problem.

**Reason codes** (fixed vocabulary, so the pool is analysable):
`illegible`, `wrong-reading`, `rubric-interpretation`, `partial-credit`,
`missing-work`, `wrong-student`, `alternative-method`, `injection`, `other`.

### B.2 Data flow

```text
teacher click ──► Label (Firestore `labels`)
                     │
     ┌───────────────┼───────────────────────────┐
     ▼               ▼                           ▼
 calibration     claim evidence (Block A)   per-reviewer stats
 pool (Block G)   weight 0.6 / 1.0          (agreement, decision_ms)
     │
     ▼
 train/dev/test assignment, frozen by hash(submission_id) — never re-shuffled
```

Assignment to split is by a stable hash of `submission_id`, decided once at
label time. This is what makes Block G possible at all: a label can never move
from test into train because someone re-ran a script.

### B.3 GCP mapping

| Component | Primitive |
|---|---|
| Labels | Firestore `labels` collection (one doc per criterion decision) |
| Pool materialisation | Cloud Run job, weekly, writes a versioned `calibration/` snapshot to GCS |
| Split assignment | Deterministic hash, no service required |
| Analysis | Optional BigQuery export for reviewer-agreement statistics |

### B.4 Budget *(target)*

Labels are a by-product of clicks that already happen: **$0 in model spend**.
Audit-sample overhead is teacher time — 10 % more cards, and only for
auto-synced records, so 3 cards on a 30-exam assessment. Storage is trivial
(one small document per criterion decision).

The real cost is downstream: a 60-exam calibration set makes each tournament
cycle ~15× the measured $0.63, i.e. **≈ $9.50 per 3-candidate cycle** *(target,
scaled linearly from the measured run)*. That is the number that argues for
running tournaments on a schedule, not per job.

### B.5 Failure containment

- Labels are append-only and never edited; a mistaken override is corrected by a
  second override that supersedes it.
- A reviewer whose agreement with other reviewers on the same items falls below a
  floor is flagged, and their labels are down-weighted — not deleted — pending a
  second opinion. Inter-rater agreement must be measured, not assumed.
- The pool builder refuses to emit a snapshot in which any single reviewer
  contributes more than 60 % of the labels for a criterion, so one person's
  idiosyncrasy cannot become the school's ground truth.

### B.6 The question it answers

> *What is the engine's real agreement with this school's teachers, on this
> school's handwriting — and is it improving?*

Measured on the random-control stratum, which is the only unbiased view of
production quality that exists.

---

## 4. Block C — Adversarial self-play

> One handwritten attack, counted four times across four documents, is the entire
> evidence base for the armor (F-15). The armor also fails open (F-13).

### C.1 Mechanism

A scheduled campaign, not a test suite:

1. **Generator agent** (Flash-Lite) receives the attack taxonomy, the current
   armor instruction, and the last 30 nights of results; it proposes N new
   payloads per class, biased toward classes with the lowest recent catch rate.
2. **Renderer** (deterministic, extends `scripts/sample_batch/`) draws each
   payload onto a real exam page at a chosen position, ink, scale and rotation,
   and produces the degraded variants from the degradation grid.
3. **Arena** runs each page through the *production* armor path and the
   *production* grading path, in an isolated bucket prefix and Firestore
   namespace, with the SIS connector replaced by a null sink.
4. **Scorer** records, per attack class: `caught`, `grade_moved`
   (Δ score vs. the same page without the payload — the metric that actually
   matters), `quarantined`, `armor_error`.
5. **Innocent control set** runs in the same campaign: pages that legitimately
   mention grading, AI, teachers or perfect scores. Catch rate without
   false-positive rate is meaningless.
6. Results assert `armor` claims (`attack_class X is caught`) with a 30-day
   half-life, so an untested class goes dormant automatically.

**First-class metrics**, published on the console next to the optimizer report:

| Metric | Definition | Bar *(target)* |
|---|---|---|
| Catch rate | caught / attempted, per class and overall | ≥ 0.95 overall, ≥ 0.80 in every class |
| **Grade-move rate** | share where \|Δ score\| > 0.5 vs. the clean twin | ≤ 0.01 — the real security property |
| False-positive rate | innocent pages flagged | ≤ 0.02 |
| Armor-error rate | screens that threw and failed open | ≤ 0.001, alarmed at any non-zero |
| Time-to-catch | nights between a class first evading and first being caught | ≤ 3 |

### C.2 GCP mapping

| Component | Primitive |
|---|---|
| Campaign driver | Cloud Run job + Cloud Scheduler, nightly |
| Isolation | Dedicated bucket prefix `redteam/{date}/`, Firestore collection prefix `rt_`, null SIS sink |
| Payload store | GCS, versioned; every payload kept forever as a regression case |
| Reporting | Firestore `armor` claims + a console panel |

Note that the bucket currently triggers the deployed pipeline on **any** upload
(F-35), so the campaign needs either a separate bucket or a notification filter
before it can run at all. That is a prerequisite, not a detail.

### C.3 Budget *(target)*

| Item | Per night | Cost |
|---|---|---|
| 20 attacks × (1 armor call + 1 grading call + 1 clean-twin grading call) | 60 calls | ≈ 20 × ($0.0391 × 2 + $0.001) ≈ **$1.58** |
| Generator | 3 Flash-Lite calls | ≈ $0.02 |
| Rendering | CPU only | ≈ $0 |
| **Nightly** | | **≈ $1.60**, ≈ 3 min wall clock |
| **Monthly** | | **≈ $48** |

Anchored on the measured $0.0391 per graded exam and the measured $0.001 per
Flash-Lite page call. The clean twin is what makes grade-move measurable and it
doubles the grading cost; it is worth it.

### C.4 Failure containment

- The campaign runs with a service account that has **no SIS access and no write
  access to production Firestore collections**.
- A hard cap on nightly spend; the job aborts on exceeding it and records the
  abort as an `operational` claim.
- Generated payloads are stored but never enter the L2 corpus — no path exists
  from red-team text into grading context (which is itself an attack class the
  campaign must test: second-order injection, §Bench T-RED class 10).

### C.5 The question it answers

> *Which attack classes currently move a grade, and how long does the system take
> to close a class once it starts failing?*

---

## 5. Block D — Evidence-coverage confidence

> Replace a self-report measured to be constant (F-01) with a quantity that can
> only be earned: the fraction of a grade that is backed by a quote a machine
> found on the page. This requires the transcript path GCP mode lacks (F-04).

### D.1 Mechanism

**The missing transcript.** Add a `transcribe` step between `fetch` and `grade`.
For each page, one Flash-Lite call returns a structured transcript: ordered text
blocks with normalised text, a bounding box, and a page index. The transcript is
written next to the object as `<object>.transcript.json` in the same bucket
(versioned, so it is auditable) and cached by content hash — a re-graded page is
never re-transcribed.

This single step converts `SidecarTextProvider` from a local-mode curiosity into
a production component: `sidecar_texts_from_batch` is replaced by a provider that
reads the transcript artefact, **keyed by page**, which also fixes the page
binding defect (F-05).

**Coverage as the numerator.** For each criterion score:

```text
verified_spans  = spans whose normalised quote is found in the transcript
                  of the page they cite, with ≥ 8 tokens or ≥ 25 characters
coverage        = verified_spans / max(1, required_spans_for_criterion)
locality        = 1 if every verified span's bbox lies inside the answer region
                  for that criterion, else 0.5
legibility      = existing deterministic metric, but computed on the
                  transcript's bounding boxes (local, not page-global — fixes F-02)
confidence_eff  = coverage × locality × legibility_local
```

`confidence_eff` replaces `criterion.confidence` as the gate input. The model's
self-report is still recorded — as telemetry, never as a gate input, weight 0.00
in Block A.

**Consequences that fall out for free:**

- A hallucinated quote can no longer pass a whole-file substring test.
- The `evidence.span_match` telemetry attribute stops lying, because a provider
  now exists (F-04).
- Quarantine volume becomes *controllable*: coverage is continuous and varies
  with page quality, unlike a constant 0.98.
- The rework loop must apply the same computation, closing F-03.

### D.2 Data flow

```text
fetch ─► transcribe ─► transcript.json (GCS, versioned, content-hash cached)
                            │
              ┌─────────────┼──────────────┐
              ▼             ▼              ▼
        grading context  faithfulness  local legibility
        (optional)        verifier      per answer region
                              │
                              ▼
                    coverage × locality × legibility
                              │
                              ▼
                        ConfidenceGate  ─► sync or quarantine
```

### D.3 GCP mapping

| Component | Primitive |
|---|---|
| Transcription | Vertex `gemini-3.5-flash-lite`, structured output, one call per page |
| Transcript store | GCS alongside the page; bucket versioning is already enabled |
| Cache key | Object generation + SHA-256, checked before calling |
| Optional upgrade | Document AI OCR as the transcript source instead of an LLM (see Block E: it is also a second reader) |

### D.4 Budget *(target)*

| Item | Per exam | Basis |
|---|---|---|
| Transcription call | ≈ $0.0023 (≈ 1 900 in + ≈ 700 out on Flash-Lite) | The measured audit call is $0.00107/exam with 1 718 in / 223 out; transcription returns more text |
| Added wall clock | ≈ +4 s per batch at fan-out | Audit stage measured 3.2 s for 8 concurrent Flash-Lite image calls |
| Per-exam cost change | $0.0391 → **≈ $0.0414 (+6 %)** | |
| 8-exam batch | 43.9 s → **≈ 48 s**, $0.313 → **≈ $0.331** | |

A 6 % cost increase to convert the defensibility guarantee from a claim into a
measurement is the best-value item in this document.

### D.5 Failure containment

- Transcription failure → the exam is **quarantined**, never graded with
  `coverage = 1.0`. The current fail-open default (`page_text is None → faithful`)
  is inverted: no transcript means no auto-sync.
- Transcript disagreement with the grader's reading is not an error — it is the
  signal. Low coverage routes to review with both readings shown.
- Cache poisoning is prevented by keying on object generation *and* content
  hash.

### D.6 The question it answers

> *What fraction of every grade is backed by text a second process actually found
> on the page — and does that fraction predict human disagreement?*

The second half is the validation: coverage is only a good confidence measure if
low coverage correlates with teacher overrides in the Block B label pool.

---

## 6. Block E — Cross-model dissent

> The grader is `gemini-3.5-flash`; the armor is `gemini-3.5-flash-lite`; the
> rework evaluator is `gemini-3.5-flash-lite`; the proposer is
> `gemini-3.5-flash-lite`. Four roles, one family, one correlated failure mode
> (F-15), behind a floating alias that can change silently (F-30).

### E.1 Mechanism

A **structurally different checker** runs on every submission, and its
disagreement — not its score — gates high-stakes writes.

Two implementations, in preference order:

| Option | Independence | Cost/page *(target)* | Notes |
|---|---|---|---|
| **E-a. Deterministic OCR + rules** | Highest: no LLM in the path | ≈ $0.0015 (Document AI list price — must be verified against the current price sheet) | Document AI OCR → numeric/symbolic extraction → a rule engine that checks what *can* be checked deterministically: arithmetic identities, algebraic factorisations (symbolic expansion), unit conversions, final-answer matching |
| **E-b. Different model family** | Medium: different training lineage | ≈ 1× a grading call | Only warranted where deterministic rules cannot express the criterion (prose, interpretation) |

For the current mathematics rubric, E-a covers two of three criteria outright:
`factoring` is a symbolic identity check (expand the claimed factors, compare to
the original polynomial), and the unit conversion in `word-problem` is
arithmetic. That is exactly the class of error the measured batch contains —
tomas-vega factoring `(x+1)(x+6)` and converting 1 h 20 min to 1.2 h — and a
deterministic checker catches both without a model.

**Dissent, not replacement.** The checker never produces the grade. It produces:

```text
dissent = { criterion_id, checker_verdict, machine_score, delta_bucket, basis }
```

**Gating rule** — a write is *high-stakes* when any of these hold:

| Condition | Rationale |
|---|---|
| The record would change a term mastery bucket | A bucket change is what a parent notices |
| Score is in the bottom band (fail/at-risk) | Asymmetric harm |
| The submission carries an armor flag | Adversarial context |
| Evidence coverage < 0.8 (Block D) | The primary reading is weak |

For high-stakes writes, **dissent blocks auto-sync**: the record is quarantined
with both readings rendered side by side. For low-stakes writes, dissent is
recorded as evidence (weight 0.40 when it *agrees*) and sampled into the label
pool (Block B) at 100 %.

### E.2 GCP mapping

| Component | Primitive |
|---|---|
| OCR | Document AI (or the Block D transcript, if the transcript source is Document AI rather than Gemini — one call serves both blocks) |
| Rule engine | Pure Python in the service; a deterministic module beside `agents/risk_signals.py`, with the same "math, not opinion" discipline as the risk detector |
| Different-family option | Any second provider reachable from Cloud Run; the `GradingEvaluator` Protocol seam already exists and is how local mode swaps implementations |

### E.3 Budget *(target)*

| Configuration | Per exam | 8-exam batch |
|---|---|---|
| E-a on every exam | +$0.0015 + negligible CPU | +$0.012, +≈1 s |
| E-b on high-stakes only (≈ 15 % of records) | +$0.0391 × 0.15 ≈ +$0.006 | +$0.047 |
| Both | ≈ +$0.008 per exam (+20 %) | ≈ $0.38 per batch |

### E.4 Failure containment

- The checker cannot write a grade, cannot call the SIS, and cannot raise the
  confidence of a record — it can only lower trust or leave it unchanged.
  A checker compromise degrades throughput, never correctness.
- Checker unavailability → high-stakes writes quarantine (fail closed), everything
  else proceeds with a recorded `checker_unavailable` note.
- Disagreement rate is itself monitored: if the checker disagrees with the grader
  on more than a threshold share of a batch, that is a batch-level alarm feeding
  the same breaker family (a wrong rubric produces exactly this signature).

### E.5 The question it answers

> *On what fraction of grades do two structurally independent readers disagree,
> and when they do, who is right?*

The second half is answerable only through Block B labels — which is why these
two blocks ship together.

---

## 7. Block F — Drift sentinels

> Nothing in the system can currently see a model version change, a cohort
> change, or a slow shift in a criterion (F-30, F-33).

### F.1 Mechanism

Three sentinels, all deterministic, all cheap:

| Sentinel | Cadence | Compares | Alarms on |
|---|---|---|---|
| **Golden replay** | Weekly + on every detected model-version change | A frozen 30-page reference set, regraded, against its stored reference scores | Any per-criterion mean shift > 0.25, or any bucket flip on a page that has never flipped |
| **Cohort sentinel** | Per batch | This batch's score distribution against the trailing 5 batches for the same class and rubric | KS statistic > 0.3, or mean shift > 1σ of the trailing distribution |
| **Term sentinel** | End of term | This term's per-criterion distribution against the same term last year, and against the same cohort's previous term | Population Stability Index > 0.25 per criterion |

Each alarm asserts a refutation against the relevant `prompt` or `rubric` claim
(Block A), which is what pulls the affected assessments into the regrade queue.

**Separating the three causes.** A distribution shift has three candidate
explanations, and the sentinels are designed to distinguish them:

| Observed | Golden replay | Cohort sentinel | Conclusion |
|---|---|---|---|
| Shifted | Shifted | Shifted | **Model or prompt drift** — the frozen pages changed, so the reader changed |
| Stable | Shifted | — | **Cohort change** — the reader is stable, the students differ |
| Stable | Stable | Shifted | **Term/curriculum change** — investigate rubric or teaching |

This is the only way to tell "the model got worse" from "this class is weaker",
and no amount of production monitoring without a frozen reference set can do it.

### F.2 GCP mapping

| Component | Primitive |
|---|---|
| Golden set | GCS, versioned, immutable prefix `golden/v1/`; reference scores in Firestore |
| Replay runner | Cloud Run job + Cloud Scheduler |
| Model-version detection | Record the resolved model id and any version metadata returned by Vertex per call; a change asserts an `operational` claim and triggers a replay |
| Statistics | Deterministic Python; no LLM in this block at all |

### F.3 Budget *(target)*

| Item | Cadence | Cost |
|---|---|---|
| Golden replay, 30 pages | Weekly | 30 × $0.0391 ≈ **$1.17** |
| Cohort sentinel | Per batch | $0 (arithmetic on results already computed) |
| Term sentinel | Per term | $0 |
| **Monthly** | | **≈ $5** |

### F.4 Failure containment

- Sentinels only *raise* claims; they never gate a live batch on their own. A
  false alarm costs a regrade queue, not a blocked term.
- The golden set is immutable and versioned; changing it requires a new version
  and re-baselining, recorded as an explicit decision.
- If the golden replay itself fails (quota, outage) the sentinel asserts
  `unknown`, which decays — an unmonitored week visibly loses confidence rather
  than silently passing.

### F.5 The question it answers

> *Did the reader change, or did the students?*

---

## 8. Block G — Label economy and holdout discipline

> The optimizer selects on the same four samples it evaluates on (F-08), the gate
> is statistically empty at that N (F-09), the proposer can copy the answer key
> into few-shots (F-10), and the agreement statistic pools criteria with
> different ceilings (F-11).

### G.1 Mechanism

| Change | Detail |
|---|---|
| **Three-way split, assigned at label time** | `hash(submission_id) mod 100`: 0–59 train, 60–79 dev, 80–99 test. Never re-shuffled, never re-assigned. The test split is readable by exactly one code path: the promotion report |
| **Promote on dev, report on test** | Tournaments select on dev. The winner is evaluated once on test. A variant that has touched test more than once is disqualified |
| **Gate on the lower confidence bound** | Promotion requires the **lower bound of a 1 000-sample bootstrap CI over exams** (not criterion pairs — errors cluster within a page) to clear the bar: `QWK_lower ≥ 0.85`, `MAE_upper ≤ 0.4`, `|bias|_upper < 0.1` |
| **Minimum N enforced in code** | The engine refuses to promote below 30 test exams / 90 criterion pairs and logs the required N (see the table in F-09) |
| **Per-criterion metrics, not pooled** | QWK computed per criterion on its own scale; the composite is the minimum across criteria, not the pooled value |
| **Few-shot inspection** | The anti-gaming validator gains three checks: reject a candidate whose few-shots contain any calibration `submission_id`; reject if any numeric literal in a few-shot matches a ground-truth score for a set member; reject if few-shot text has > 0.9 similarity to any calibration page transcript |
| **Ties promote when simpler** | Replace strict `improvement > 0` with: promote on a tie only if the candidate is strictly shorter or removes a rule — otherwise keep the incumbent. Prevents the measured "a0 tied and was rejected" dead end without opening the door to noise-chasing |

### G.2 Budget *(target)*

Scaling the measured tournament ($0.6296 for 4 exams × 4 variant evaluations):

| Set size | Per 3-candidate cycle | Notes |
|---|---:|---|
| 4 exams (today) | $0.63 | measured |
| 30 exams (dev) | ≈ $4.70 | the minimum N that makes the gate meaningful |
| 60 exams (dev) | ≈ $9.40 | comfortable margin |
| Test evaluation, 20 exams, once per promotion | ≈ $0.80 | rare by construction |

Monthly, at one scheduled tournament per week on a 30-exam dev set:
**≈ $20** *(target)*.

### G.3 Failure containment

The test split is enforced by construction: the calibration loader exposes
`train()` and `dev()` only; `test()` lives in a separate module used solely by
the promotion reporter, and using it stamps the variant with `test_touched += 1`.

### G.4 The question it answers

> *Is this prompt actually better, or did we pick the winner of a coin flip?*

---

## 9. Block H — Completeness ledger

> Exams currently vanish (F-16) and large uploads silently truncate (F-27). No
> amount of learning matters if the input set is wrong.

### H.1 Mechanism

| Change | Detail |
|---|---|
| **Roster-anchored manifest** | The expected submission set comes from the class roster (or an explicit manifest), not from a bucket listing at a moment in time. A batch is `complete` only when every roster entry has a terminal state |
| **Terminal states for every submission** | `graded` · `quarantined` · `isolated` · `missing`. `isolated` and `missing` **create review items** — an exam that crashed the grader is a human's problem, not a log line |
| **Breaker denominator = expected, not survivors** | `BatchAnomalyBreaker.evaluate(expected_count, quarantined + isolated + missing)` |
| **Late-arrival reconciliation** | An `OBJECT_FINALIZE` for a prefix whose job already completed enqueues an **amendment job** for the new objects instead of returning `duplicate`. Amendment jobs write only the new records and never rewrite existing facts |
| **Lease-based claiming** | Replace the in-process `claimed_jobs` set with a Firestore lease document (owner, heartbeat, TTL), so two instances cannot both start a job (F-28) and a dead instance's job is recoverable without the 600 s stale-checkpoint heuristic |
| **Bounded fan-out** | A semaphore around the grading gather sized from settings; a 150-exam batch grades in waves instead of issuing 150 concurrent calls (F-29) |

### H.2 Budget

Arithmetic and Firestore writes: **$0 in model spend.** Bounded fan-out trades
wall clock for reliability — at concurrency 16, a 150-exam batch is ≈ 10 waves ×
≈ 25 s ≈ **4 minutes** *(target, from the measured 16–26 s per-exam grading
span)*, still far inside the 900 s request timeout and the 600 s ack deadline.

### H.3 The question it answers

> *For every exam a school put in the bucket, where is it now?* The answer must
> be a complete partition with no residual category.

---

## 10. Block I — Version pinning and shadow replay

| Change | Detail |
|---|---|
| Pin the model to a dated snapshot rather than a floating alias, and record the pin in provenance | A grade becomes reproducible |
| On an intentional version bump, run the golden replay (Block F) and a shadow pass over the last 200 production submissions before switching | A version change becomes a measured event, not a surprise |
| Persist every promoted `PromptVariant` to the `prompts` collection at promotion time, and add `GET /prompts/{sha}` | Makes the provenance receipt resolvable (F-07) |

Budget *(target)*: a 200-submission shadow pass ≈ 200 × $0.0391 ≈ **$7.82**, run
once per model change.

---

## 11. Staging

### Now — this term (targets the S1/S2 findings; no new ML)

| # | Item | Blocks | Why now |
|---|---|---|---|
| 1 | Completeness ledger, roster anchoring, breaker denominator, review items for `isolated`/`missing` | H | F-16 loses grades today |
| 2 | Amendment jobs for late arrivals + lease-based claiming + bounded fan-out | H | F-27 is the large-batch killer |
| 3 | Transcript step + evidence-coverage confidence + local legibility | D | Converts the defensibility guarantee into a measurement for +6 % cost |
| 4 | Apply the coverage gate inside the rework loop | D, F-03 | One-line class of bug, high blast radius |
| 5 | Override endpoint + labels on approve/dismiss/override | B | Every day without it is labels thrown away |
| 6 | Armor: fail **closed**, and quarantine on screen error | C, F-13 | A security control must not fail open silently |
| 7 | Persist promoted prompt variants; `GET /prompts/{sha}` | I | Makes existing receipts resolvable |
| 8 | Raise the ingest object cap and stream large batches | H, F-26 | The documented teacher path is blocked at 41 files |

### Next term (needs labels and a schedule)

| # | Item | Blocks | Prerequisite |
|---|---|---|---|
| 9 | Claim ledger + `assessment_facts` + projections replacing overwrites | A | Migration of existing profiles |
| 10 | Nightly challenge runner and dispute escalation | A | Block 9 |
| 11 | Deterministic OCR + rules checker; dissent gating on high-stakes writes | E | Transcript step (item 3) |
| 12 | Red-team campaign, nightly, with catch rate and grade-move on the console | C | Bucket/notification isolation (F-35) |
| 13 | Golden replay + cohort + term sentinels | F | A frozen golden set |
| 14 | Three-way split, bootstrap CIs, per-criterion gates, few-shot inspection | G | ≥ 60 labelled exams from Block B |
| 15 | Scheduled tournaments (weekly) replacing the per-job optimize stage, with a visible "did not run" state | G, F-12 | Block 14 |

### Research (open questions, not schedulable)

| # | Question |
|---|---|
| R1 | Does evidence coverage predict teacher override better than any self-reported confidence? Requires ≥ 300 labels across both quarantined and control strata |
| R2 | What is the right decay half-life per scope? Set here by argument; it should be fitted so that a claim's confidence tracks its empirical hit rate |
| R3 | Can the red team beat the armor faster than the armor adapts — and is a co-evolving pair stable, or does it collapse into a degenerate attack/defence pair? |
| R4 | Does deterministic symbolic checking generalise beyond mathematics? For prose criteria the independent reader has to be a model, and independence becomes an assumption rather than a property |
| R5 | Are the dropout thresholds real? Requires a cohort with known outcomes and a pre-registered evaluation, and it is the only block here that touches student welfare directly |
| R6 | Inter-rater agreement between teachers on the same page: if human labels disagree at QWK 0.75, no gate at 0.85 against a single human is meaningful |

---

## 12. Total cost envelope *(target)*

Per-batch changes, using the measured 8-exam batch as the unit:

| Configuration | Per exam | 8-exam batch | Δ vs. today |
|---|---:|---:|---:|
| Today (measured) | $0.0391 | $0.313 / 43.9 s | — |
| + transcript & coverage (D) | $0.0414 | $0.331 / ≈ 48 s | +6 % |
| + deterministic checker (E-a) | $0.0429 | $0.343 / ≈ 49 s | +10 % |
| + high-stakes second model (E-b, 15 %) | $0.0488 | $0.390 / ≈ 52 s | +25 % |

Scheduled work, per month *(target)*:

| Block | Monthly |
|---|---:|
| A — challenge runner (nightly) | ≈ $6 |
| C — red team (nightly) | ≈ $48 |
| F — golden replay (weekly) | ≈ $5 |
| G — tournaments (weekly, 30-exam dev) | ≈ $20 |
| I — shadow replay (per model change) | ≈ $8 each |
| **Total scheduled** | **≈ $80 / month** |

For scale: a school grading 2 000 exams a term pays ≈ $78 in grading at today's
per-exam cost, ≈ $86 with blocks D and E-a. The reflective plane roughly doubles
the bill and is the only part of the system that can tell the school whether the
other half is working.
