import re

from autocurricula.core.harness import PageTextProvider
from autocurricula.schemas.armor import ArmorSeverity, ArmorVerdict
from autocurricula.schemas.exam import ExamSubmission

QUOTE_WINDOW = 100

INJECTION_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"ignore\s+(?:the\s+|all\s+|any\s+)?(?:rubric|instructions?|grading)",
        r"disregard\s+(?:the\s+|all\s+)?(?:rubric|instructions?)",
        r"give\s+(?:me\s+|us\s+|him\s+|her\s+)?full\s+marks",
        r"(?:award|assign|give|grant|set)\s+(?:me\s+|us\s+|him\s+|her\s+|them\s+)?"
        r"(?:a\s+|the\s+)?(?:full|perfect|maximum|max)\s+"
        r"(?:marks?|scores?|grades?|credit)",
        r"system\s+note",
        r"you\s+are\s+(?:the\s+)?(?:grader|grading\s+system|ai|assistant)",
        r"(?:teacher|instructor)\s+(?:has\s+)?already\s+approved",
        r"grade\s+this\s+(?:a\s+|as\s+)?(?:100|perfect)",
        r"(?:score|grade|mark)\s+(?:this|it|me|him|her|them)\s+(?:at\s+|as\s+|with\s+)?"
        r"(?:the\s+)?(?:maximum|max|full|perfect|10|100)",
    )
)


def scan_page_text(text: str) -> tuple[str, str] | None:
    for pattern in INJECTION_PATTERNS:
        match = pattern.search(text)
        if match is None:
            continue
        window = text[match.start() : match.start() + QUOTE_WINDOW].strip()
        return window, pattern.pattern
    return None


class ScriptedInjectionDetector:
    def __init__(self, provider: PageTextProvider) -> None:
        self._provider = provider

    async def screen(self, submission: ExamSubmission) -> ArmorVerdict:
        pages = max((file.page_count for file in submission.files), default=0)
        for page in range(1, pages + 1):
            text = self._provider.page_text(submission.submission_id, page)
            if not text:
                continue
            hit = scan_page_text(text)
            if hit is None:
                continue
            quote, pattern = hit
            return ArmorVerdict(
                injection_detected=True,
                quoted_text=quote,
                severity=ArmorSeverity.HIGH,
                rationale=(
                    f"page {page} contains text addressed to the grading system "
                    f"(scripted pattern {pattern!r})"
                ),
            )
        return ArmorVerdict(
            injection_detected=False,
            rationale="no grader-directed instructions found in page transcripts",
        )
