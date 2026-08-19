# Dev log — Feedback 001: operational friction, governance and ROI

**Date:** 2026-08-13
**Domain:** Product feedback
**Source:** Stakeholder (review of the "product: inputs and outputs" entry)
**Status:** Accepted — planned in `2026-08-13-plan-001`

## 1. The operational-friction blind spot: who fills the manifest?

**Problem:** if the teacher must create a JSON or fill a form per batch, the
promise "the teacher uploads files and disappears" breaks.

**Requested improvement:** the manifest must be **inferrable automatically**
from file/folder naming conventions in the bucket (e.g.
`2026_Matematicas_10A_Parcial1.pdf`) or via a pre-printed cover page with a
QR/OCR code read at the FETCH stage.

## 2. The governance guarantee: confidence-gated quarantine

**Problem:** in formal K-12, writing 100% of grades straight to the SIS
without prior validation triggers institutional rejection (fear of litigation
or parent complaints).

**Requested improvement:** an explicit guarantee — "if the multimodal
extraction confidence or the evidence sharpness falls below **85%**, the grade
is not synced directly: it stays in `REQUIRES_HUMAN_REVIEW` with the page and
the exact visual excerpt pre-highlighted so the teacher can approve it with
one click."

## 3. Quantitative ROI metrics

- **Teacher time saved:** from ~12 weekly hours of manual grading to zero
  transcription and ~10 minutes of exception review.
- **Time-to-feedback:** feedback cycle reduced from 14 days to under 10
  minutes after the scan is uploaded.

## 4. Optimized pitch version (for the README)

**Elevator pitch:** "In goes a batch of scanned exams; out come audited grades
in the SIS, curriculum coverage maps and early dropout alerts. The teacher
does not use an app or learn interfaces: they drop files and get their
evenings back. Pure backoffice infrastructure."

**New input-flow matrix:**

| Input | Source | Frequency |
|---|---|---|
| Batch of scanned exams (handwritten PDFs/images) | Teacher or front office | Per assessment |
| Batch metadata (subject, grade, active rubric) | **Auto-inferred from the path or lot-code convention** | Automatic per event |
| Rubrics and national curriculum standard | Pedagogical coordination | Once per term |
| Calibration samples (human ground truth) | Validated historical assessments | Periodic (feeds self-improvement) |
| SIS/LMS credentials and connectors | IT / administration | One-time setup |

**Fundamental guarantees (new formulation):**

1. **Transactional idempotency:** even if Pub/Sub delivers the message
   multiple times, an exam is never duplicated or computed twice in the SIS.
2. **Absolute defensibility:** every grade includes an `EvidenceSpan` with a
   verbatim quote and page number; complaints are answered with evidence from
   the student's own manuscript.
3. **Confidence-threshold escalation:** ambiguous answers or illegible
   handwriting are never guessed: they go to quarantine for quick teacher
   validation.
4. **Deterministic, explainable risk:** alerts are based on mathematical
   trends (z-scores, longitudinal slopes over L3), not free-form LLM opinion.
5. **Anti-gaming self-improvement:** the optimizer only promotes variants that
   improve human agreement (QWK/MAE), actively blocking variance collapse or
   artificial average-to-middle grades.
6. **Long-running fault tolerance:** persistent per-stage checkpoints; the
   flow resumes exactly at the pending stage without recomputing prior work.
