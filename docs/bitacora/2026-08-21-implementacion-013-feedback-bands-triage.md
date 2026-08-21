# Dev log — Implementation 013: developmental feedback bands and the triage surface

**Date:** 2026-08-21
**Domain:** Implementation
**Fulfills:** SOL-020 (age-appropriate student feedback; teacher surface that survives a held batch)
**Verification:** offline suite **503 passed / 8 skipped** (was 420/8; +83 tests); four live grading runs across bands; headless-browser walkthrough of the triage flow.

## Feedback that knows how old the student is

Until now the engine wrote one free-text paragraph, in whatever register the
model chose, identical for a seven-year-old and a seventeen-year-old.
`schemas/feedback.py` introduces `StudentFeedback` — headline, strengths and
growth points each anchored to a cited `EvidenceSpan`, exactly one `next_step`,
and a `teacher_note` that is never shown to the student. The band
(early primary / upper primary / lower secondary / upper secondary) is derived
**in code** from the rubric grade level and stamped over whatever the model
claims; an unparseable level drops the object rather than guessing.

The prompt work is grounded in named frameworks, each with the concrete output
rule it forces (documented in `docs/architecture/student-feedback.md`):
feed-up/feed-back/feed-forward gives the object its shape; the person-versus-
process praise literature bans ability attributions; cognitive-load work caps
points at two per side and forbids a compound next step; closing-the-gap
requires every point to quote the student's own line; and the mark-cancels-the-
comment finding keeps scores, percentages, criterion ids and any hint of a
machine grader out of student-facing text.

Honesty rules: a malformed feedback object is salvaged by re-validating the
grade without it — bad feedback can never cost a grade — and nothing is ever
fabricated.

**What the live runs exposed** (`docs/reports/feedback-bands-2026-08-21.md`):
the first pass at early primary retreated to praising handwriting ("You write
neat numbers and letters on your page") because the ten-word ceiling left
nothing else sayable — precisely the content-free praise the design exists to
remove. The contract now requires a strength to name a subject action and
forbids praising neatness, effort or speed; the same page then produced "Your
number 22 C shows the highest temperature." The measured register gradient
across the four bands is monotone in headline length, next-step length and
longest sentence, with no word counting in code.

## A teacher surface that survives a held batch

With 100 students, one tripped circuit breaker puts 63 exams in the queue at
once — and the previous design asked for 63 identical clicks, which guarantees
rubber-stamping. The surface now opens on a triage of two groups: the exams
held for a reason of their own (injection, illegible scan, low confidence,
failed grading) reviewed one at a time; and the exams held **only** by the
batch rule, released together behind one confirmation. Sixty-three tasks
become four decisions.

The separation is enforced server-side, not by hiding buttons: the bulk
endpoint refuses any item carrying a reason beyond the batch-anomaly one and
reports which ids it refused and why. Releases are idempotent, write to the SIS
per student so provenance stays individual, and emit one durable human label
each — the same label the single-approve path emits.

## Follow-up recorded rather than hidden

The bounded rework loop re-grades with an evaluator that is not band-bound, so
a reworked record carries only the free-text feedback. One-line fix in
`rework_loop.py`, deliberately left for the next cycle because it sits outside
the ownership boundaries of this one.
