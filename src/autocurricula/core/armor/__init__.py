from autocurricula.core.armor.legibility import (
    DEFAULT_CONFIDENCE_FLOOR,
    DEFAULT_FULL_TRUST_LEGIBILITY,
    batch_legibility,
    confidence_factor,
    legibility_score,
)
from autocurricula.core.armor.scripted import (
    INJECTION_PATTERNS,
    ScriptedInjectionDetector,
    scan_page_text,
)
from autocurricula.core.armor.wiring import (
    ARMOR_RESULT_KEY,
    InjectionDetector,
    build_injection_detector,
    flagged_students,
    injection_reason,
    load_armor_report,
    resolve_injection_detector,
    resolve_legibility,
    screen_submission,
    store_armor_report,
)

__all__ = [
    "ARMOR_RESULT_KEY",
    "DEFAULT_CONFIDENCE_FLOOR",
    "DEFAULT_FULL_TRUST_LEGIBILITY",
    "INJECTION_PATTERNS",
    "InjectionDetector",
    "ScriptedInjectionDetector",
    "batch_legibility",
    "build_injection_detector",
    "confidence_factor",
    "flagged_students",
    "injection_reason",
    "legibility_score",
    "load_armor_report",
    "resolve_injection_detector",
    "resolve_legibility",
    "scan_page_text",
    "screen_submission",
    "store_armor_report",
]
