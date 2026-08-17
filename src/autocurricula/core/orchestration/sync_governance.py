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

SIS_WRITE_TOOL = "sis.write_grades"

GovernancePartition = tuple[
    set[str], dict[str, list[str]], dict[str, list[EvidenceSpan]], dict[str, list[str]], dict[str, float]
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
    batch: ExamBatch, grade_result: GradingBatchResult, gate: ConfidenceGate
) -> GovernancePartition:
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
        verdict = gate.evaluate(result)
        all_cited = all(
            criterion.evidence for criterion in result.criterion_scores
        )
        effective = min(
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
        reasons.setdefault(student_id, []).extend(verdict.reasons)
    return quarantined_students, reasons, evidence, documents, confidences


def build_provenance(
    student_id: str,
    grade_result: GradingBatchResult,
    prompt_variant: PromptVariant | None,
    spans: list[EvidenceSpan],
) -> Provenance:
    model_sha = model_id_sha(grade_result.model_id)
    if prompt_variant is None:
        return Provenance(
            prompt_variant_id=grade_result.model_id,
            prompt_version_sha=model_sha,
            evidence_hashes=[evidence_sha(span) for span in spans],
            model_sha=model_sha,
        )
    return Provenance(
        prompt_variant_id=f"{prompt_variant.variant_id}@v{prompt_variant.version}",
        prompt_version_sha=prompt_version_sha(prompt_variant),
        evidence_hashes=[evidence_sha(span) for span in spans],
        model_sha=model_sha,
    )
