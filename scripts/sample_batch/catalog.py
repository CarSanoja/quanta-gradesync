import base64
import json
from typing import Any

from sample_batch.lots import (
    GRADE_LEVEL,
    REFERENCE_LOT,
    SUBJECT,
    LotSpec,
)

CLASS_ID = REFERENCE_LOT.class_id
LOT_CODE = REFERENCE_LOT.lot_code
BATCH_PREFIX = REFERENCE_LOT.batch_prefix
RUBRIC_ID = "mat-10a-parcial1"
JOB_ID = REFERENCE_LOT.job_id
TRIGGERED_AT = REFERENCE_LOT.triggered_at
TRACE_ID = REFERENCE_LOT.trace_id

CRITERION_FACTORING = "factoring"
CRITERION_GRAPH = "graph-reading"
CRITERION_WORD_PROBLEM = "word-problem"

MAX_SCORES = {
    CRITERION_FACTORING: 4.0,
    CRITERION_GRAPH: 3.0,
    CRITERION_WORD_PROBLEM: 3.0,
}

QUESTIONS = {
    CRITERION_FACTORING: (
        "1. Factor completely and justify each step:  x^2 + 5x + 6"
    ),
    CRITERION_GRAPH: (
        "2. The graph shows classroom temperature from 08:00 to 12:00. "
        "Describe the change between 09:00 and 10:00 and state the maximum."
    ),
    CRITERION_WORD_PROBLEM: (
        "3. A school bus travels 84 km in 1 h 20 min. Find its average speed "
        "and show the unit conversion."
    ),
}


def _mastery(no_evidence: str, developing: str, proficient: str, advanced: str) -> dict[str, str]:
    return {
        "no_evidence": no_evidence,
        "developing": developing,
        "proficient": proficient,
        "advanced": advanced,
    }


def build_rubric() -> dict[str, Any]:
    return {
        "rubric_id": RUBRIC_ID,
        "subject": SUBJECT,
        "version": 1,
        "criteria": [
            {
                "criterion_id": CRITERION_FACTORING,
                "description": "Factors a quadratic trinomial and justifies the factor pair",
                "weight": 1.0,
                "max_score": MAX_SCORES[CRITERION_FACTORING],
                "mastery_descriptions": _mastery(
                    "No factoring work is present on the page.",
                    "Attempts a factor pair but the product or sum is wrong.",
                    "Correct factors with a partial justification.",
                    "Correct factors, verified product and sum, and a written check.",
                ),
            },
            {
                "criterion_id": CRITERION_GRAPH,
                "description": "Reads a time series graph and reports change and maximum",
                "weight": 1.0,
                "max_score": MAX_SCORES[CRITERION_GRAPH],
                "mastery_descriptions": _mastery(
                    "No reading of the graph is recorded.",
                    "Reports a trend without values or units.",
                    "Reports the change with values and identifies the maximum.",
                    "Reports change, units, maximum and the time it occurs.",
                ),
            },
            {
                "criterion_id": CRITERION_WORD_PROBLEM,
                "description": "Solves an average speed problem with unit conversion",
                "weight": 1.0,
                "max_score": MAX_SCORES[CRITERION_WORD_PROBLEM],
                "mastery_descriptions": _mastery(
                    "No solution attempt is present.",
                    "Sets up the ratio but does not convert the time correctly.",
                    "Correct conversion and speed with minor notation gaps.",
                    "Correct conversion, speed, units and an interpretation sentence.",
                ),
            },
        ],
    }


def build_curriculum_standard() -> dict[str, Any]:
    competencies = [
        (
            "MAT.10.1",
            "Factors polynomial expressions and justifies the procedure used.",
        ),
        (
            "MAT.10.2",
            "Interprets tables and graphs of real situations, reporting change and extrema.",
        ),
        (
            "MAT.10.3",
            "Models proportional situations with units and validates the result.",
        ),
    ]
    return {
        "country": "CO",
        "version": "2026.1",
        "competencies": [
            {
                "code": code,
                "description": description,
                "grade_level": GRADE_LEVEL,
                "subject": SUBJECT,
            }
            for code, description in competencies
        ],
    }


def build_catalog_defaults() -> dict[str, Any]:
    return {
        "bindings": [
            {
                "subject": SUBJECT,
                "grade_level": GRADE_LEVEL,
                "rubric": build_rubric(),
                "curriculum_standard": build_curriculum_standard(),
            }
        ]
    }


def build_job_event(bucket: str, lot: LotSpec = REFERENCE_LOT) -> dict[str, Any]:
    return {
        "job_id": lot.job_id,
        "bucket": bucket,
        "exam_batch_prefix": lot.batch_prefix,
        "class_id": lot.class_id,
        "subject": SUBJECT,
        "triggered_at": lot.triggered_at,
        "trace_id": lot.trace_id,
    }


def build_push_body(bucket: str, lot: LotSpec = REFERENCE_LOT) -> dict[str, Any]:
    payload = json.dumps(build_job_event(bucket, lot), sort_keys=True)
    encoded = base64.b64encode(payload.encode("utf-8")).decode("ascii")
    return {
        "message": {
            "messageId": lot.message_id,
            "data": encoded,
            "attributes": {"lot_code": lot.lot_code},
        },
        "subscription": "projects/quanta-gradesync/subscriptions/exam-batch-ingest-push",
    }


def build_ground_truth(
    entries: list[dict[str, Any]], lot: LotSpec = REFERENCE_LOT
) -> dict[str, Any]:
    total_ceiling = sum(MAX_SCORES.values())
    students = []
    for entry in entries:
        scores = entry["scores"]
        total = round(sum(scores.values()), 2)
        students.append(
            {
                "student_id": entry["student_id"],
                "submission_id": entry["student_id"],
                "criterion_scores": scores,
                "total_score": total,
                "percentage": round(100.0 * total / total_ceiling, 2),
                "grader": "human-calibration",
                "notes": entry["notes"],
            }
        )
    return {
        "job_id": lot.job_id,
        "lot_code": lot.lot_code,
        "rubric_id": RUBRIC_ID,
        "subject": SUBJECT,
        "class_id": lot.class_id,
        "max_scores": MAX_SCORES,
        "students": students,
    }
