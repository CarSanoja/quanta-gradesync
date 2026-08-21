from dataclasses import dataclass

from autocurricula.core.armor.encoding import (
    TECHNIQUE_PLAIN,
    derived_variants,
    normalize_identifier,
)
from autocurricula.core.armor.scripted import scan_page_text


@dataclass(frozen=True)
class DeterministicHit:
    quote: str
    pattern: str
    technique: str


def _hit(text: str, technique: str) -> DeterministicHit | None:
    found = scan_page_text(text)
    if found is None:
        return None
    quote, pattern = found
    return DeterministicHit(quote=quote, pattern=pattern, technique=technique)


def scan_derived(text: str) -> DeterministicHit | None:
    for candidate, technique in derived_variants(text):
        hit = _hit(candidate, technique)
        if hit is not None:
            return hit
    return None


def scan_text(text: str) -> DeterministicHit | None:
    plain = _hit(text, TECHNIQUE_PLAIN)
    if plain is not None:
        return plain
    return scan_derived(text)


def scan_identifier(value: str) -> DeterministicHit | None:
    normalized = normalize_identifier(value)
    for candidate in (value, normalized):
        hit = scan_text(candidate)
        if hit is not None:
            return hit
    return None
