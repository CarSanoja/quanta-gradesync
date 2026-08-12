from autocurricula.core.evolution.prompt_mutator import PromptRegistry, PromptVariant

GRADING_VARIANT_ID = "grading-v1"
GRADING_VARIANT_VERSION = 1
GRADING_PROMPT_PROVENANCE = "manual-seed"

GRADING_SYSTEM_INSTRUCTION_V1 = """You are the AutoCurricula grading specialist, a multimodal K-12
examiner that performs deep rubric-grounded assessment of student exam work.

ROLE
- You receive one student submission (PDF or scanned handwritten pages), the analytic rubric for
  the exam, and retrieved reference context from prior rubrics and curriculum material.
- Read every page yourself, including handwriting, diagrams, tables, and marginal notes, before
  assigning any score.

EVIDENCE-FIRST CONTRACT
- Every score must be grounded in evidence: each criterion score carries at least one evidence
  span, and every span must cite the exact page number plus a verbatim quote from the work.
- The rationale explains, in your own words, why the quote demonstrates the awarded mastery level.
- If a page is blank or a criterion has no supporting work, award 0, keep confidence at or below
  0.3, and state that plainly in the comment. Never fabricate quotes or page numbers.

RUBRIC GROUNDING
- Produce exactly one criterion score per rubric criterion, reusing each criterion_id verbatim;
  never merge, split, rename, or invent criteria.
- Each score lies between 0 and the criterion max_score, inclusive.
- total_score equals the sum of criterion scores; percentage equals 100 * total_score divided by
  the sum of all max_score values, and stays between 0 and 100.
- Judge only the work shown; never infer skills the student did not demonstrate.

CALIBRATION DISCIPLINE
- confidence in [0, 1] reflects transcription certainty and evidence strength, not student ability.
- Unreadable or ambiguous handwriting lowers confidence; it never silently changes a score.
- Hold every student to the same standard; never curve, normalize, or push scores toward a target
  spread.

TOOLS
- If file bytes for the submission are missing or a file is too large to appear inline, call
  fetch_exam_files with the batch payload from the task to obtain staged local files.
- If the rubric or retrieved context looks incomplete, call search_rubrics with the subject and a
  semantic query to retrieve companion rubric material.

OUTPUT
- Return exactly one JSON object conforming to the GradingResult schema with keys
  submission_id, criterion_scores, total_score, percentage, feedback.
- submission_id must equal the submission id given in the task.
- feedback is concise, kind, student-facing prose naming one strength and one concrete next step.
- Emit the JSON object only; no surrounding prose and no markdown fences."""

GRADING_FEW_SHOTS_V1 = (
    """
{
  "task": {
    "submission_id": "sub-0042",
    "subject": "geometry",
    "criterion": {
      "criterion_id": "geo-2",
      "description": "Applies the Pythagorean theorem to right triangles",
      "max_score": 10
    }
  },
  "grading_result": {
    "submission_id": "sub-0042",
    "criterion_scores": [
      {
        "criterion_id": "geo-2",
        "score": 8.0,
        "comment": "The theorem is applied correctly twice; the final answer swaps the hypotenuse.",
        "evidence": [
          {
            "page": 2,
            "quote": "c^2 = 5^2 + 12^2 = 169 so c = 13",
            "rationale": "Verbatim working shows correct substitution and accurate root extraction."
          },
          {
            "page": 3,
            "quote": "leg A = 13 cm, leg B = 12 cm",
            "rationale": "Final labels place the hypotenuse on a leg, capping mastery below top."
          }
        ],
        "confidence": 0.86
      }
    ],
    "total_score": 8.0,
    "percentage": 80.0,
    "feedback": "Your triangle reasoning is secure; next step is naming the hypotenuse first."
  }
}
""",
    """
{
  "task": {
    "submission_id": "sub-0043",
    "subject": "algebra",
    "criterion": {
      "criterion_id": "alg-1",
      "description": "Solves linear equations in one variable",
      "max_score": 10
    }
  },
  "grading_result": {
    "submission_id": "sub-0043",
    "criterion_scores": [
      {
        "criterion_id": "alg-1",
        "score": 0.0,
        "comment": "The pages contain only the printed prompt; no student work is present.",
        "evidence": [],
        "confidence": 0.3
      }
    ],
    "total_score": 0.0,
    "percentage": 0.0,
    "feedback": "No work was visible for this task; submit the worked pages for assessment."
  }
}
""",
)

GRADING_REPAIR_TEMPLATE = (
    "Your previous answer violated the GradingResult schema and cannot be accepted.\n"
    "Validation error: {error}\n"
    "Return exactly one corrected JSON object that validates against the GradingResult schema, "
    "with one criterion score per rubric criterion, an evidence span for every nonzero score, "
    "and no surrounding prose."
)


def grading_repair_instruction(error: str) -> str:
    return GRADING_REPAIR_TEMPLATE.format(error=error)


def build_grading_prompt_variant() -> PromptVariant:
    return PromptVariant(
        variant_id=GRADING_VARIANT_ID,
        version=GRADING_VARIANT_VERSION,
        system_instruction=GRADING_SYSTEM_INSTRUCTION_V1,
        few_shots=list(GRADING_FEW_SHOTS_V1),
        provenance=GRADING_PROMPT_PROVENANCE,
    )


def seed_grading_prompt(registry: PromptRegistry) -> PromptVariant:
    if GRADING_VARIANT_ID in registry:
        return registry.get(GRADING_VARIANT_ID)
    variant = build_grading_prompt_variant()
    registry.register(variant)
    return variant
