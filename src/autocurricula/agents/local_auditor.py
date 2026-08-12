import re

from autocurricula.schemas.curriculum import CurriculumAuditResult, CurriculumStandard
from autocurricula.schemas.grading import CriterionScore, GradingResult
from autocurricula.schemas.memory import RetrievedContext

LOCAL_MAPPING_OVERLAP = 0.2
LOCAL_STRONG_OVERLAP = 0.35
_MIN_TOKEN_LENGTH = 3
_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "that",
        "this",
        "from",
        "have",
        "has",
        "are",
        "was",
        "were",
        "will",
        "shall",
        "into",
        "when",
        "where",
        "which",
        "while",
        "their",
        "them",
        "they",
        "than",
        "then",
        "been",
        "being",
        "does",
        "done",
        "each",
        "very",
        "must",
        "also",
        "such",
        "some",
        "any",
        "all",
        "can",
        "may",
        "not",
        "but",
        "its",
        "his",
        "her",
        "our",
        "you",
        "who",
        "how",
        "why",
        "what",
        "use",
        "used",
        "using",
        "show",
        "shows",
        "shown",
    }
)


def _tokenize(text: str) -> set[str]:
    return {
        token
        for token in _TOKEN_PATTERN.findall(text.lower())
        if len(token) >= _MIN_TOKEN_LENGTH and token not in _STOPWORDS
    }


def _containment(needles: set[str], haystack: set[str]) -> float:
    if not needles:
        return 0.0
    return len(needles & haystack) / len(needles)


def _criterion_text(criterion: CriterionScore) -> str:
    parts = [criterion.comment]
    for span in criterion.evidence:
        parts.extend([span.quote, span.rationale])
    return " ".join(parts)


def _context_text(context: RetrievedContext) -> str:
    parts = [context.query]
    parts.extend(chunk.text for chunk in context.chunks)
    return " ".join(parts)


class LocalCurriculumAuditor:
    def __init__(
        self,
        *,
        mapping_overlap: float = LOCAL_MAPPING_OVERLAP,
        strong_overlap: float = LOCAL_STRONG_OVERLAP,
    ) -> None:
        if not 0.0 < mapping_overlap <= strong_overlap:
            raise ValueError(
                "mapping_overlap must be positive and not exceed strong_overlap"
            )
        self._mapping_overlap = mapping_overlap
        self._strong_overlap = strong_overlap

    async def audit(
        self,
        result: GradingResult,
        standard: CurriculumStandard,
        context: RetrievedContext,
    ) -> CurriculumAuditResult:
        context_text = _context_text(context)
        context_tokens = _tokenize(context_text)
        competency_tokens = {
            competency.code: _tokenize(
                f"{competency.description} {competency.subject} {competency.grade_level}"
            )
            for competency in standard.competencies
        }
        mappings: dict[str, list[str]] = {}
        for criterion in result.criterion_scores:
            tokens = _tokenize(_criterion_text(criterion))
            if not tokens:
                continue
            matched = [
                code
                for code, tokens_for_code in competency_tokens.items()
                if self._supports(
                    tokens, tokens_for_code, code, context_text, context_tokens
                )
            ]
            if matched:
                mappings[criterion.criterion_id] = sorted(matched)
        covered = sorted({code for codes in mappings.values() for code in codes})
        missing = sorted(set(competency_tokens) - set(covered))
        notes = (
            f"local deterministic audit: {len(mappings)} criteria mapped, "
            f"{len(covered)} of {len(standard.competencies)} competencies covered, "
            f"overlap threshold {self._mapping_overlap}"
        )
        return CurriculumAuditResult(
            submission_id=result.submission_id,
            mappings=mappings,
            covered_codes=covered,
            missing_codes=missing,
            notes=notes,
        )

    def _supports(
        self,
        criterion_tokens: set[str],
        competency_tokens: set[str],
        competency_code: str,
        context_text: str,
        context_tokens: set[str],
    ) -> bool:
        direct = _containment(criterion_tokens, competency_tokens)
        if direct >= self._strong_overlap:
            return True
        if direct < self._mapping_overlap:
            return False
        return competency_code in context_text or bool(
            competency_tokens & context_tokens
        )
