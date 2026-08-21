# Student feedback — developmental register as an engineered field

| | |
|---|---|
| **Status** | Shipped in this cycle: `StudentFeedback` is produced by the grading agent and carried to the SIS record and the review item |
| **Audience** | Engineers touching the grading prompt or the sync path; pedagogical coordination reviewing what the engine writes to children |
| **Date** | 2026-08-21 |
| **Premise** | A grade is a number; feedback is an intervention. An intervention written in the wrong register for the reader is not a weaker intervention, it is a different one |
| **Evidence** | [feedback-bands-2026-08-21](../reports/feedback-bands-2026-08-21.md) — the same real exam page graded live under four bands |

---

## 1. The problem this replaces

Before this cycle the engine wrote two things to a student: one free-text
`feedback` paragraph and one `comment` per rubric criterion. Both were written
in whatever register the model happened to choose, and both were identical in
shape for a seven-year-old and a seventeen-year-old. The register was an
accident of decoding, not a decision. Nothing in the system knew the age of the
reader, and nothing constrained the failure modes that the formative assessment
literature has documented for forty years — ability praise, generic
encouragement, a list of five things to fix, and teacher vocabulary aimed at a
child.

The fix is structural, not stylistic: feedback becomes a **typed field with a
band**, the band is **derived in code** from the grade level bound to the
rubric, and the prompt carries a **per-band contract** that names the register,
the sentence budget, the shape of the next step, and the prohibitions.

## 2. The pedagogy, and what each framework changes in the output

Every rule below exists because a specific finding demands it. A rule with no
finding behind it is not in the prompt.

| Framework | Claim being applied | What it changes in the emitted object |
|---|---|---|
| **Hattie & Timperley (2007), *The Power of Feedback*** — feed-up / feed-back / feed-forward, and the four levels (task, process, self-regulation, self) | Feedback must answer *where am I going*, *how am I going*, *where to next*; feedback at the **self** level (praise of the person) is the least effective level and can depress performance | The object has three parts in that order: `headline` (where the work stands against what the task asked), `strengths` + `growth` (how it is going, with evidence from the page), `next_step` (where to next). The band decides whether the growth points sit at the **task** level (early primary) or climb to **process** and **self-regulation** (lower and upper secondary) |
| **Mueller & Dweck (1998), person vs. process praise** | Praising ability produces contingent self-worth, helplessness after failure and lower persistence; praising the process sustains effort | The contract forbids `smart, clever, brilliant, gifted, talented, a natural, good at this, bad at this, lazy, careless` and any other praise or blame of ability or character. A strength must name a **subject action the student performed**, never handwriting, neatness, effort or speed |
| **Shute (2008), *Focus on Formative Feedback*** | Specific and task-focused beats general; feedback must be manageable in size; comparisons to other learners are counterproductive | At most two strengths and two growth points (one and one at early primary); **exactly one** `next_step`, never two joined by "and"; comparison to classmates or to an average is forbidden |
| **Sadler (1989), closing the gap** | The learner must hold a concept of the standard, be able to compare their work against it, and possess an action that closes the distance | Each growth point is anchored to an `EvidenceSpan` quoting the student's own line, and the band decides how the standard is expressed: something visible on the page (early primary) up to a named, standard-referenced target (upper secondary). `next_step` must act on one of the growth points just named — never a new topic, never a habit that would fit any exam |
| **Butler (1988); Black & Wiliam (1998)** | A mark printed beside a comment cancels the comment: students read the mark and stop | The student-facing text never states or hints at the score, points, percentage, grade, mastery level, criterion id, rubric wording or confidence. Those travel in their own fields and in `teacher_note` |
| **Weiner, attribution; growth-oriented locus of control** | Outcomes attributed to controllable, unstable causes (strategy, a specific move) sustain agency; stable-trait attributions do not | Growth is phrased as **the next attempt** ("next time, write the unit beside each number"), never as a deficit label ("you do not understand units"). At lower secondary and above the result is explicitly attributed to the method chosen |
| **Vygotsky (ZPD); Piaget (concrete → formal operational); Flavell (1979) and Brown (1987) on metacognition** | The action must be reachable with the support available; abstraction, hypothetical reasoning and self-monitoring come online across these ages, and metacognitive prompts pay off only once the learner can monitor a strategy | The four bands: early primary demands **no self-monitoring** at all (the step is done, not planned); upper primary asks for **one light checking habit**; lower secondary asks for **one self-check on their own work**; upper secondary asks for **self-regulation** — the student sets and monitors the target |

## 3. The four bands

The band is derived from the grade level, never asked of the model and never
inferred from the work. `band_for_grade_level` in
`src/autocurricula/schemas/feedback.py` parses the grade level bound to the
rubric (`ExamBatch.grade_level`, which the catalog binding carries beside the
rubric), and maps K–12 onto four bands. Anything it cannot parse — an empty
value, "adult", grade 13 — returns **no band**, and no band means no student
feedback at all rather than a guessed register.

| | `early_primary` (K–3) | `upper_primary` (4–6) | `lower_secondary` (7–9) | `upper_secondary` (10–12) |
|---|---|---|---|---|
| Sentence budget | ≤ 10 words, one clause | ≤ 15 words | ≤ 20 words | no ceiling, no padding |
| Vocabulary | everyday words only | everyday + one subject word, explained | subject vocabulary expected | criterion language in plain words |
| Evidence anchor | something visible on their own page | their own line, and what it shows | a quoted step, named (setup, units, justification) | a quoted step and its distance from the standard |
| Points | 1 strength, 1 growth | ≤ 2 and ≤ 2 | ≤ 2 and ≤ 2 | ≤ 2 and ≤ 2 |
| `next_step` | one visible action, ≤ 12 words, doable alone | one strategy for the same kind of problem + the check that shows it worked | one procedure carried into the next attempt, stated as a rule | one standard-referenced target + the evidence the student uses to judge it |
| Metacognitive demand | none | one light checking habit | one self-check, result attributed to the method | self-regulation: the student sets and monitors the target |

`teacher_note` is the pressure valve that keeps the student text clean: rubric
ids, mastery language, diagnostic hypotheses and the model's own uncertainty go
there, and it is never shown to the student.

## 4. Where the band enters the call

The grading evaluator is a process-wide singleton, so the band cannot be baked
into its system instruction. Two things happen instead:

1. **The seed system instruction carries the whole contract and all four bands**
   (`feedback_section()` composed into `GRADING_SYSTEM_INSTRUCTION_V1`), so the
   prompt optimizer sees the rules it is allowed to mutate.
2. **Each call carries its own band block** (`band_task_block(band)`, appended
   in `build_grading_parts`). The block is self-sufficient: band name, that
   band's register rules and the full contract. A promoted tournament variant
   that mutated the feedback section away therefore still receives band
   guidance — the register does not depend on which prompt variant is active.

`bind_feedback_band(evaluator, grade_level)` in the grade stage returns a
**bound copy** of the evaluator for the batch; the shared instance is never
mutated, so two jobs at different grade levels can run concurrently.

```text
catalog binding (grade_level) ─► ExamBatch.grade_level
        │
        ▼  band_for_grade_level()            deterministic, in code
   FeedbackBand ──► bind_feedback_band(evaluator, grade_level)
        │                    │
        │                    ▼  band_task_block() appended to the user message
        │              grading call ──► GradingResult.student_feedback
        ▼
   stamp_feedback_band()  ──► the engine's band overwrites whatever the model wrote
        │
        ▼
 SISGradeRecord.student_feedback ──► SIS write  ·  ReviewItem.proposed_record
```

## 5. Honesty rules

The system may write nothing to a student, but it may never write something it
did not read on the page.

- **The band is stamped by the engine after parsing.** If the model returns a
  different band, the derived one wins. If no band could be derived, any
  volunteered `student_feedback` is dropped to `None`.
- **Unusable feedback never costs a grade.** If the response fails validation
  because of `student_feedback`, the schema-repair retry runs as before; if it
  still fails, `salvage_without_student_feedback` re-validates the same payload
  with that key removed. The grade, the criterion scores, the evidence and the
  free-text `feedback` ship; `student_feedback` stays `None`.
- **Both fields coexist this cycle.** The flat `feedback` string keeps its place
  in `GradingResult`, `SISGradeRecord` and every consumer that already reads it.
  `student_feedback` is additive and optional, so a record graded before this
  change still validates and still renders.
- **No fabrication.** The contract instructs the model to omit
  `student_feedback` entirely rather than write something generic when the page
  cannot support it.

## 6. What this does not do yet

- **The rework path produces no student feedback.** The bounded rework loop
  re-grades quarantined submissions through a second-opinion evaluator that is
  not band-bound, and `rework_loop._record_for` rebuilds the SIS record without
  the field. A reworked record therefore carries the free-text feedback only.
  Closing this is two lines in `core/orchestration/rework_loop.py` (bind the
  band from `context.batch.grade_level`, pass `result.student_feedback` into the
  record) and is deliberately left to the owner of that file.
- **The band is a proxy for developmental stage, not a measurement of it.** A
  grade level is what the engine has; reading age, language of instruction and
  additional needs are not modelled. The bands are deliberately wide (three to
  four grades) so that the proxy error stays inside the band.
- **The headline is less constrained than the strengths.** The prohibition on
  praising neatness and effort applies to strengths; the live runs show the
  headline can still drift to a surface observation when the content is far
  above the band. See the [report](../reports/feedback-bands-2026-08-21.md).
- **No readability metric is enforced in code.** Sentence budgets are prompt
  instructions, not validators. A post-hoc word-count check per band is the
  obvious next control, and would make register regressions visible to the
  calibration loop rather than to a reader.
