import base64
import binascii
import re
import unicodedata

TECHNIQUE_PLAIN = "plain"
TECHNIQUE_UNICODE = "unicode-folded"
TECHNIQUE_LEET = "leetspeak"
TECHNIQUE_REVERSED = "reversed"
TECHNIQUE_BASE64 = "base64"

INVISIBLE_CHARS = "\u200b\u200c\u200d\u2060\u180e\ufeff\u00ad"

HOMOGLYPHS = {
    "а": "a",
    "в": "b",
    "е": "e",
    "к": "k",
    "м": "m",
    "н": "h",
    "о": "o",
    "р": "p",
    "с": "c",
    "т": "t",
    "у": "y",
    "х": "x",
    "ѕ": "s",
    "і": "i",
    "ј": "j",
    "һ": "h",
    "α": "a",
    "ε": "e",
    "ι": "i",
    "κ": "k",
    "ν": "v",
    "ο": "o",
    "ρ": "p",
    "τ": "t",
    "υ": "u",
    "χ": "x",
}

LEET = {
    "0": "o",
    "1": "i",
    "3": "e",
    "4": "a",
    "5": "s",
    "7": "t",
    "@": "a",
    "$": "s",
}

MIN_DECODED_CHARS = 8
MIN_TEXT_RATIO = 0.75
BASE64_TOKEN = re.compile(r"[A-Za-z0-9+/]{16,}={0,2}")
SEPARATORS = re.compile(r"[\W_]+")
CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")

_INVISIBLE_TABLE = dict.fromkeys(map(ord, INVISIBLE_CHARS))
_HOMOGLYPH_TABLE = str.maketrans(
    {**HOMOGLYPHS, **{key.upper(): value for key, value in HOMOGLYPHS.items()}}
)
_LEET_TABLE = str.maketrans(LEET)


def strip_invisible(text: str) -> str:
    return unicodedata.normalize("NFKC", text.translate(_INVISIBLE_TABLE))


def fold_homoglyphs(text: str) -> str:
    return strip_invisible(text).translate(_HOMOGLYPH_TABLE)


def has_confusables(text: str) -> bool:
    return any(char in HOMOGLYPHS or char in INVISIBLE_CHARS for char in text)


def deleet(text: str) -> str:
    return text.translate(_LEET_TABLE)


def looks_like_text(value: str) -> bool:
    if len(value) < MIN_DECODED_CHARS or not value.isprintable():
        return False
    readable = sum(1 for char in value if char.isalpha() or char.isspace())
    return readable >= MIN_TEXT_RATIO * len(value)


def decode_base64_tokens(text: str) -> list[str]:
    decoded: list[str] = []
    for match in BASE64_TOKEN.finditer(text):
        token = match.group(0).rstrip("=")
        padding = -len(token) % 4
        if padding == 3:
            continue
        try:
            raw = base64.b64decode(token + "=" * padding, validate=True).decode("utf-8")
        except (binascii.Error, ValueError, UnicodeDecodeError):
            continue
        if looks_like_text(raw):
            decoded.append(raw)
    return decoded


def normalize_identifier(value: str) -> str:
    folded = CAMEL_BOUNDARY.sub(" ", fold_homoglyphs(value))
    return SEPARATORS.sub(" ", folded).strip().lower()


def derived_variants(text: str) -> tuple[tuple[str, str], ...]:
    folded = fold_homoglyphs(text)
    candidates = [
        (folded, TECHNIQUE_UNICODE),
        (deleet(folded), TECHNIQUE_LEET),
        (folded[::-1], TECHNIQUE_REVERSED),
    ]
    candidates.extend((item, TECHNIQUE_BASE64) for item in decode_base64_tokens(text))
    seen = {text}
    variants: list[tuple[str, str]] = []
    for candidate, technique in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        variants.append((candidate, technique))
    return tuple(variants)
