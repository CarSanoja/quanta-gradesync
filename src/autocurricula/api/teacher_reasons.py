BATCH_HELD = "This whole batch was held for a human look as a precaution."
INJECTION_FOUND = (
    "This page contains written instructions addressed to the grader — review carefully."
)
BLURRY_SCAN = "This scan is blurry — please confirm the grade yourself."
NO_QUOTE = "The grade doesn't quote anything from the page — please double-check it."
NOT_SURE = "The grading wasn't sure about this one — please confirm it yourself."
COULD_NOT_GRADE = "This exam could not be graded — it needs manual grading."
LATE_SCAN = "This scan arrived after grading started — it has not been graded."
FALLBACK_REASON = "This exam is waiting for your decision before the grade goes out."

KEY_BATCH_HELD = "batch_hold"
KEY_INJECTION = "injection"
KEY_LEGIBILITY = "legibility"
KEY_FAILED = "failed"
KEY_LATE = "late"
KEY_NO_QUOTE = "no_evidence"
KEY_UNSURE = "low_confidence"
KEY_OTHER = "other"

REASON_TRANSLATIONS: tuple[tuple[str, str, str], ...] = (
    ("batch anomaly", KEY_BATCH_HELD, BATCH_HELD),
    ("prompt injection", KEY_INJECTION, INJECTION_FOUND),
    ("legibility", KEY_LEGIBILITY, BLURRY_SCAN),
    ("could not be graded", KEY_FAILED, COULD_NOT_GRADE),
    ("arrived after grading started", KEY_LATE, LATE_SCAN),
    ("no cited evidence", KEY_NO_QUOTE, NO_QUOTE),
    ("below threshold", KEY_UNSURE, NOT_SURE),
)


def match_reason(reason: str) -> tuple[str, str]:
    lowered = reason.lower()
    for needle, key, message in REASON_TRANSLATIONS:
        if needle in lowered:
            return key, message
    return KEY_OTHER, FALLBACK_REASON


def translate_reason(reason: str) -> str:
    return match_reason(reason)[1]


def reason_key(reason: str) -> str:
    return match_reason(reason)[0]


def translate_reasons(reasons: list[str]) -> list[str]:
    return list(dict.fromkeys(translate_reason(reason) for reason in reasons))
