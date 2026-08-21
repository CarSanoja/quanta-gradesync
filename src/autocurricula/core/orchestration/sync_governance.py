import logging

from autocurricula.core.evolution.prompt_mutator import PromptVariant
from autocurricula.core.harness import (
    ActionRisk,
    PermissionDecision,
    Provenance,
    ToolAction,
    evidence_sha,
    manifest_scope_gate,
    model_id_sha,
    prompt_version_sha,
)
from autocurricula.core.review import ConfidenceGate
from autocurricula.schemas.exam import ExamBatch
from autocurricula.schemas.grading import EvidenceSpan, GradingBatchResult
from autocurricula.schemas.sis_sync import SISGradeRecord
from autocurricula.schemas.telemetry import VERIFICATION_UNCHECKED

logger = logging.getLogger(__name__)

SIS_WRITE_TOOL = "sis.write_grades"

GovernancePartition = tuple[
    set[str],
    dict[str, list[str]],
    dict[str, list[EvidenceSpan]],
    dict[str, list[str]],
    dict[str, float],
]


def build_sis_permission_gate(
    manifest_students: set[str], confidence_threshold: float
):
    return manifest_scope_gate(
        manifest_students, SIS_WRITE_TOOL, "min_confidence", confidence_threshold
    )


def sis_action(record: SISGradeRecord, min_confidence: float) -> ToolAction:
    return ToolAction(
        tool=SIS_WRITE_TOOL,
        target=record.student_id,
        risk=ActionRisk.EXTERNAL_MUTATION,
        payload={"min_confidence": min_confidence},
    )


def partition_by_gate(
    batch: ExamBatch,
    grade_result: GradingBatchResult,
    gate: ConfidenceGate,
    *,
    confidence_factors: dict[str, float] | None = None,
    legibility: dict[str, float] | None = None,
) -> GovernancePartition:
    factors = confidence_factors or {}
    scores = legibility or {}
    student_by_submission = {
        submission.submission_id: submission.student_id
        for submission in batch.submissions
    }
    quarantined_students: set[str] = set()
    reasons: dict[str, list[str]] = {}
    evidence: dict[str, list[EvidenceSpan]] = {}
    documents: dict[str, list[str]] = {}
    confidences: dict[str, float] = {}
    for submission in batch.submissions:
        paths = documents.setdefault(submission.student_id, [])
        paths.extend(file.gcs_uri for file in submission.files)
    for result in grade_result.results:
        student_id = student_by_submission.get(result.submission_id)
        if student_id is None:
            continue
        factor = factors.get(student_id, 1.0)
        verdict = gate.evaluate(result, confidence_factor=factor)
        all_cited = all(
            criterion.evidence for criterion in result.criterion_scores
        )
        effective = factor * min(
            (criterion.confidence for criterion in result.criterion_scores),
            default=0.0,
        )
        if not all_cited:
            effective = 0.0
        confidences[student_id] = min(
            confidences.get(student_id, 1.0), effective
        )
        spans = evidence.setdefault(student_id, [])
        spans.extend(
            span
            for criterion in result.criterion_scores
            for span in criterion.evidence
        )
        if not verdict.quarantined:
            continue
        quarantined_students.add(student_id)
        student_reasons = reasons.setdefault(student_id, [])
        if factor < 1.0:
            student_reasons.append(
                _legibility_reason(scores.get(student_id), factor)
            )
        student_reasons.extend(verdict.reasons)
    return quarantined_students, reasons, evidence, documents, confidences


def _legibility_reason(score: float | None, factor: float) -> str:
    measured = f"{score:.2f}" if score is not None else "unknown"
    return (
        f"low scan legibility: score {measured} discounted model confidence "
        f"by factor {factor:.2f}"
    )


def partition_records(
    records: list[SISGradeRecord],
    permission,
    confidences: dict[str, float],
    armor_flagged: dict[str, str],
) -> tuple[list[SISGradeRecord], list[SISGradeRecord]]:
    auto_records: list[SISGradeRecord] = []
    quarantined_records: list[SISGradeRecord] = []
    for record in records:
        verdict = permission.evaluate(
            sis_action(record, confidences.get(record.student_id, 0.0))
        )
        if verdict.decision == PermissionDecision.DENY:
            logger.warning(
                "harness denied sis write for out-of-manifest target %s",
                record.student_id,
            )
        elif (
            record.student_id in armor_flagged
            or verdict.decision == PermissionDecision.QUARANTINE
        ):
            quarantined_records.append(record)
        else:
            auto_records.append(record)
    return auto_records, quarantined_records


def build_provenance(
    student_id: str,
    grade_result: GradingBatchResult,
    prompt_variant: PromptVariant | None,
    spans: list[EvidenceSpan],
    faithfulness_checked: bool | None = None,
) -> Provenance:
    model_sha = model_id_sha(grade_result.model_id)
    variant_id = (
        grade_result.model_id
        if prompt_variant is None
        else f"{prompt_variant.variant_id}@v{prompt_variant.version}"
    )
    version_sha = (
        model_sha if prompt_variant is None else prompt_version_sha(prompt_variant)
    )
    return Provenance(
        prompt_variant_id=variant_id,
        prompt_version_sha=version_sha,
        evidence_hashes=[evidence_sha(span) for span in spans],
        model_sha=model_sha,
        faithfulness_checked=faithfulness_checked,
    )


def faithfulness_by_student(
    batch: ExamBatch, statuses: dict[str, str]
) -> dict[str, bool]:
    checked: dict[str, bool] = {}
    for submission in batch.submissions:
        status = statuses.get(submission.submission_id, VERIFICATION_UNCHECKED)
        confirmed = status != VERIFICATION_UNCHECKED
        student = submission.student_id
        checked[student] = confirmed and checked.get(student, True)
    return checked


def stamp_provenance(
    records: list[SISGradeRecord],
    grade_result: GradingBatchResult,
    prompt_variant: PromptVariant | None,
    evidence: dict[str, list[EvidenceSpan]],
    checked: dict[str, bool],
) -> dict[str, SISGradeRecord]:
    return {
        record.student_id: record.model_copy(
            update={
                "provenance": build_provenance(
                    record.student_id,
                    grade_result,
                    prompt_variant,
                    evidence.get(record.student_id, []),
                    checked.get(record.student_id, False),
                )
            }
        )
        for record in records
    }
