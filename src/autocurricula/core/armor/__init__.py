from autocurricula.core.armor.deterministic import (
    DeterministicHit,
    scan_derived,
    scan_identifier,
    scan_text,
)
from autocurricula.core.armor.encoding import (
    decode_base64_tokens,
    derived_variants,
    has_confusables,
    normalize_identifier,
)
from autocurricula.core.armor.legibility import (
    DEFAULT_CONFIDENCE_FLOOR,
    DEFAULT_FULL_TRUST_LEGIBILITY,
    batch_legibility,
    confidence_factor,
    legibility_score,
)
from autocurricula.core.armor.metadata import (
    is_safe_identifier,
    manifest_strings,
    prompt_safe_submission,
    redacted_token,
    safe_identifier,
    safe_path,
    screen_metadata,
)
from autocurricula.core.armor.prescreen import (
    PrescreenedDetector,
    deterministic_screen,
    screen_page_encodings,
)
from autocurricula.core.armor.scripted import (
    INJECTION_PATTERNS,
    ScriptedInjectionDetector,
    scan_page_text,
)
from autocurricula.core.armor.transcripts import (
    RawSidecarProvider,
    raw_provider_for,
    raw_sidecar_texts,
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
    "DeterministicHit",
    "InjectionDetector",
    "PrescreenedDetector",
    "RawSidecarProvider",
    "ScriptedInjectionDetector",
    "batch_legibility",
    "build_injection_detector",
    "confidence_factor",
    "decode_base64_tokens",
    "derived_variants",
    "deterministic_screen",
    "flagged_students",
    "has_confusables",
    "injection_reason",
    "is_safe_identifier",
    "legibility_score",
    "load_armor_report",
    "manifest_strings",
    "normalize_identifier",
    "prompt_safe_submission",
    "raw_provider_for",
    "raw_sidecar_texts",
    "redacted_token",
    "resolve_injection_detector",
    "resolve_legibility",
    "safe_identifier",
    "safe_path",
    "scan_derived",
    "scan_identifier",
    "scan_page_text",
    "scan_text",
    "screen_metadata",
    "screen_page_encodings",
    "screen_submission",
    "store_armor_report",
]
