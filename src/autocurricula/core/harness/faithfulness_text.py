import re
from difflib import SequenceMatcher

_WHITESPACE = re.compile(r"\s+")

DEFAULT_MATCH_THRESHOLD = 0.75
MIN_FUZZY_QUOTE_CHARS = 12
NEAR_MATCH_RATIO = 0.9


def normalize_text(text: str) -> str:
    return _WHITESPACE.sub(" ", text.strip().lower())


SYMBOL_FOLDS = {
    "×": "*",
    "·": "*",
    "∙": "*",
    "÷": "/",
    "−": "-",
    "–": "-",
    "—": "-",
    "²": "^2",
    "³": "^3",
    "\u2019": "'",
    "\u201c": '"',
    "\u201d": '"',
}
_DECIMAL_COMMA = re.compile(r"(?<=\d),(?=\d)")


def fold_symbols(text: str) -> str:
    folded = text
    for symbol, replacement in SYMBOL_FOLDS.items():
        folded = folded.replace(symbol, replacement)
    return _DECIMAL_COMMA.sub(".", folded)


def compact_text(text: str) -> str:
    return _WHITESPACE.sub("", fold_symbols(normalize_text(text)))


def longest_common_coverage(quote: str, page_text: str) -> float:
    if not quote:
        return 1.0
    matcher = SequenceMatcher(None, quote, page_text, autojunk=False)
    match = matcher.find_longest_match(0, len(quote), 0, len(page_text))
    return match.size / len(quote)


def near_match_ratio(quote: str, page_text: str) -> float:
    if not quote or len(page_text) < len(quote):
        return 0.0
    matcher = SequenceMatcher(None, quote, page_text, autojunk=False)
    anchor = matcher.find_longest_match(0, len(quote), 0, len(page_text))
    start = max(0, anchor.b - anchor.a)
    window = page_text[start : start + len(quote)]
    return SequenceMatcher(None, quote, window, autojunk=False).ratio()
