GRADING_FEW_SHOTS_V1 = (
    """
{
  "task": {
    "submission_id": "sub-0042",
    "subject": "geometry",
    "grade_level": "11",
    "student_feedback_band": "upper_secondary",
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
    "feedback": "Your triangle reasoning is secure; next step is naming the hypotenuse first.",
    "student_feedback": {
      "band": "upper_secondary",
      "headline": "Your substitution and square root are exact; the labelling of the sides is where the work falls short of the standard.",
      "strengths": [
        {
          "text": "You substituted both legs into c^2 = a^2 + b^2 and took the root without an arithmetic slip.",
          "evidence": {
            "page": 2,
            "quote": "c^2 = 5^2 + 12^2 = 169 so c = 13",
            "rationale": "The line shows correct substitution and an exact root."
          }
        }
      ],
      "growth": [
        {
          "text": "The 13 cm side is the hypotenuse, so on the next attempt label the sides before you solve, and the answer will match the diagram.",
          "evidence": {
            "page": 3,
            "quote": "leg A = 13 cm, leg B = 12 cm",
            "rationale": "The label puts the longest side on a leg."
          }
        }
      ],
      "next_step": "On the next right-triangle question, mark the side opposite the right angle as the hypotenuse before substituting, then check that your answer is the longest side.",
      "teacher_note": "geo-2 sits at proficient: the procedure is secure, the side-naming is not. Worth one diagnostic item on identifying the hypotenuse from a diagram."
    }
  }
}
""",
    """
{
  "task": {
    "submission_id": "sub-0043",
    "subject": "algebra",
    "grade_level": "2",
    "student_feedback_band": "early_primary",
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
    "feedback": "No work was visible for this task; submit the worked pages for assessment.",
    "student_feedback": {
      "band": "early_primary",
      "headline": "This page is still empty, so there is nothing to read yet.",
      "strengths": [],
      "growth": [
        {
          "text": "Next time, write your first try under the question.",
          "evidence": null
        }
      ],
      "next_step": "Write one number sentence under the question.",
      "teacher_note": "alg-1 scored 0 for no evidence, not for an error. Check whether the page was mis-scanned before treating this as a gap."
    }
  }
}
""",
)
