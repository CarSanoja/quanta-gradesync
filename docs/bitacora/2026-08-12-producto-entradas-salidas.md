# Dev log — GradeSync as a product: what goes in, what comes out

**Date:** 2026-08-12
**Domain:** Product / value
**Status:** Current (revised by feedback 001 — see the feedback entry)

## Elevator pitch

**In goes a package of scanned exams; out come grades written into the
school's system, risk alerts and a class competency map.** The teacher does
not "use" an app: they upload files and disappear from the flow. Pure
backoffice — zero chat, zero interfaces to learn.

## What goes in

| Input | Who provides it | Frequency |
|---|---|---|
| Batch of scanned exams (PDFs/images, handwritten) | Teacher or academic office | Every assessment |
| Batch manifest — class, subject, rubric, curriculum standard | The school (template) | Every assessment |
| Current rubrics and ministry competency standard | Academic coordination | Once per term |
| Calibration samples — human-graded exams (ground truth) | Teachers | Occasional |
| Credentials and endpoints — SIS, bucket, Pub/Sub topic | School IT | Once (setup) |

## What comes out

**For the teacher:**
- Grades per criterion with cited evidence (page + verbatim quote from the
  manuscript)
- Written feedback per submission
- Minutes of turnaround instead of hours

**For academic coordination:**
- Automatic curriculum reconciliation (covered vs orphaned competencies)
- Early dropout alerts with explainable drivers and suggested interventions
- Class mastery map per competency

**For the SIS / backoffice:**
- Grade records already written, with competency codes — zero transcription

**For the engine itself:**
- Calibration reports: active prompt version, MAE/QWK/bias against humans,
  rejected mutations and why

## Product guarantees

1. Never duplicates a grade (job idempotency).
2. Never loses a half-processed batch (checkpoint resume).
3. Every grade is defensible (cites evidence from the student's own work).
4. Risk is not a black box (deterministic statistics).
5. It improves but does not cheat (optimizer anti-gaming gate).
6. Nothing degrades silently (strict contracts).

## Honest limits

- Output quality is a function of rubric and scan quality.
- The improvement loop requires human ground truth.
- Genuine illegibility → explicit, flagged failure; the product never invents
  a reading.

**In one line:** it turns hours of manual grading + transcription + curriculum
cross-referencing + eyeball risk detection into **one upload**, with an
auditable receipt for every decision.
