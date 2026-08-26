import pytest

from autocurricula.core.evolution.prompt_mutator import PromptVariant
from autocurricula.core.harness import (
    BudgetExceeded,
    ItemBudget,
    SidecarTextProvider,
    enforce_result,
    evidence_sha,
    guard_item,
    model_id_sha,
    prompt_version_sha,
    sidecar_texts_from_batch,
    span_is_faithful,
)
from autocurricula.schemas.grading import CriterionScore, EvidenceSpan, GradingResult

PROMPT = PromptVariant(
    variant_id="grading-v1",
    version=1,
    system_instruction="score with evidence",
    few_shots=["q1"],
    provenance="seed",
)


def make_result(quote: str, confidence: float = 0.9) -> GradingResult:
    return GradingResult(
        submission_id="sub-1",
        criterion_scores=[
            CriterionScore(
                criterion_id="crit-a",
                score=3.0,
                comment="ok",
                evidence=[
                    EvidenceSpan(page=1, quote=quote, rationale="visible answer")
                ],
                confidence=confidence,
            )
        ],
        total_score=3.0,
        percentage=75.0,
        feedback="ok",
    )


def test_item_budget_counts_and_raises() -> None:
    budget = ItemBudget(max_calls=2)
    budget.record_call()
    budget.record_call()
    with pytest.raises(BudgetExceeded, match="item budget exceeded"):
        budget.record_call()


async def test_guard_item_records_the_call() -> None:
    budget = ItemBudget(max_calls=2)

    async def operation() -> str:
        return "done"

    assert await guard_item(operation, budget) == "done"
    assert budget.calls == 1


def test_item_budget_rejects_invalid_limits() -> None:
    with pytest.raises(ValueError):
        ItemBudget(max_calls=0)


def test_span_is_faithful_with_normalization() -> None:
    page = "The student  Solves the equation   2x + 3 = 7 correctly."
    assert span_is_faithful("solves the equation 2x+3=7", page) is False
    assert span_is_faithful("Solves the equation 2x + 3 = 7", page) is True


def test_missing_page_text_is_treated_as_faithful() -> None:
    assert span_is_faithful("anything", None) is True


def test_enforce_result_zeroes_confidence_on_hallucinated_quote() -> None:
    provider = SidecarTextProvider({("sub-1", 1): "unrelated transcript"})
    enforced = enforce_result(make_result("ghost quote"), provider)
    assert enforced.criterion_scores[0].confidence == 0.0
    assert "faithfulness" in enforced.criterion_scores[0].comment


def test_enforce_result_keeps_faithful_result_untouched() -> None:
    provider = SidecarTextProvider({("sub-1", 1): "the cited answer text"})
    result = make_result("the cited answer text")
    assert enforce_result(result, provider) is result


def test_sidecar_texts_from_batch_reads_txt_sidecars(tmp_path) -> None:
    scan = tmp_path / "stu-1.jpg"
    scan.write_bytes(b"scan")
    sidecar = tmp_path / "stu-1.txt"
    sidecar.write_text("transcript of the page", encoding="utf-8")
    batch = type(
        "Batch",
        (),
        {
            "submissions": [
                type(
                    "Submission",
                    (),
                    {
                        "submission_id": "stu-1",
                        "files": [
                            type(
                                "File",
                                (),
                                {
                                    "local_path": str(scan),
                                    "gcs_uri": "gs://b/p/stu-1.jpg",
                                    "page_count": 1,
                                },
                            )
                        ],
                    },
                )
            ]
        },
    )()
    texts = sidecar_texts_from_batch(batch)
    assert texts[("stu-1", 1)] == "transcript of the page"


def test_prompt_version_sha_is_deterministic_and_version_sensitive() -> None:
    identical = PromptVariant(
        variant_id="grading-v1",
        version=1,
        system_instruction=PROMPT.system_instruction,
        few_shots=PROMPT.few_shots,
        provenance="other-provenance",
    )
    assert prompt_version_sha(PROMPT) == prompt_version_sha(identical)
    assert len(prompt_version_sha(PROMPT)) == 64
    bumped = PROMPT.model_copy(update={"version": 2})
    assert prompt_version_sha(PROMPT) != prompt_version_sha(bumped)
    rewritten = PROMPT.model_copy(
        update={"system_instruction": "different instruction"}
    )
    assert prompt_version_sha(PROMPT) != prompt_version_sha(rewritten)


def test_evidence_sha_is_deterministic() -> None:
    span = EvidenceSpan(page=2, quote="answer", rationale="why")
    assert evidence_sha(span) == evidence_sha(span)
    assert len(evidence_sha(span)) == 64


def test_model_id_sha_is_stable() -> None:
    assert model_id_sha("gemini-3.5-pro") == model_id_sha("gemini-3.5-pro")
