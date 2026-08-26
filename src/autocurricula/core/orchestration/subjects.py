import unicodedata

SUBJECT_ALIASES = {
    "math": "matematicas",
    "maths": "matematicas",
    "mathematics": "matematicas",
    "matematica": "matematicas",
    "matematicas": "matematicas",
    "language": "lenguaje",
    "languagearts": "lenguaje",
    "lengua": "lenguaje",
    "castellano": "lenguaje",
    "science": "ciencias",
    "sciences": "ciencias",
    "ciencia": "ciencias",
}


def strip_accents(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value)
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def normalize_token(value: str) -> str:
    return strip_accents(value).strip().lower().replace(" ", "-")


def canonical_subject(value: str) -> str:
    normalized = normalize_token(value)
    return SUBJECT_ALIASES.get(normalized.replace("-", ""), normalized)


def same_subject(left: str, right: str) -> bool:
    return canonical_subject(left) == canonical_subject(right)
