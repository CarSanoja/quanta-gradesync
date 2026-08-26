from sample_batch.profiles import (
    QUALITY_PARTIAL,
    STRIKE_PREFIX,
    StudentProfile,
    demo_profile,
)

_CORRECT_FACTORING = (
    "x^2 + 5x + 6 = (x + 2)(x + 3)",
    "Product 6 and sum 5, so the pair is 2 and 3.",
    "Check by expansion: x^2 + 3x + 2x + 6 = x^2 + 5x + 6.",
)
_CORRECT_GRAPH = (
    "Between 09:00 and 10:00 the temperature rises from 18 C to 22 C, a gain of 4 C.",
    "The maximum is 24 C at 11:00.",
)
_CORRECT_WORD = (
    "1 h 20 min = 4/3 h",
    "v = 84 / (4/3) = 63 km/h",
)


def _partial(
    student_id: str,
    display_name: str,
    ink: str,
    font_size: int,
    factoring: tuple[str, ...],
    graph: tuple[str, ...],
    word_problem: tuple[str, ...],
    notes: str,
) -> StudentProfile:
    return demo_profile(
        student_id,
        display_name,
        ink,
        font_size,
        factoring,
        graph,
        word_problem,
        quality=QUALITY_PARTIAL,
        notes=notes,
    )


PARTIAL_PROFILES: tuple[StudentProfile, ...] = (
    _partial(
        "sofia-carrillo",
        "Sofia Carrillo",
        "blue",
        30,
        (
            "x^2 + 5x + 6 = (x + 1)(x + 6)",
            "1 * 6 = 6, so these are the factors.",
        ),
        _CORRECT_GRAPH,
        _CORRECT_WORD,
        "Wrong factor pair: checks the product but never the sum.",
    ),
    _partial(
        "esteban-quiroga",
        "Esteban Quiroga",
        "black",
        32,
        ("x^2 + 5x + 6 = (x + 2)(x + 3)",),
        ("It rises 4 C between 09:00 and 10:00 and the maximum is 24 C at 11:00.",),
        ("1 h 20 min = 4/3 h", "v = 63 km/h"),
        "Right factors with no justification and no check written anywhere.",
    ),
    _partial(
        "abril-madrigal",
        "Abril Madrigal",
        "dark_blue",
        29,
        _CORRECT_FACTORING,
        (
            "Between 09:00 and 10:00 the temperature rises 4 C, from 18 C to 22 C.",
            "The maximum is 22 C.",
        ),
        _CORRECT_WORD,
        "Misreads the graph maximum as 22 C instead of 24 C.",
    ),
    _partial(
        "gaspar-uribe",
        "Gaspar Uribe",
        "graphite",
        31,
        _CORRECT_FACTORING,
        (
            "The temperature climbs 4 C between 09:00 and 10:00, 18 C to 22 C.",
            "The maximum is 24 C and it happens at 12:00.",
        ),
        _CORRECT_WORD,
        "Right maximum value, wrong hour: reports 12:00 instead of 11:00.",
    ),
    _partial(
        "renata-bonilla",
        "Renata Bonilla",
        "blue",
        28,
        _CORRECT_FACTORING,
        _CORRECT_GRAPH,
        (
            "1 h 20 min = 1.2 h",
            "v = 84 / 1.2 = 70 km/h",
        ),
        "Classic conversion error: writes 1 h 20 min as 1.2 h and gets 70 km/h.",
    ),
    _partial(
        "cristobal-figueroa",
        "Cristobal Figueroa",
        "black",
        33,
        (
            "x^2 + 5x + 6 = (x + 2)(x + 3)",
            "Product 6, sum 5.",
            "Expansion check gives the trinomial back.",
        ),
        (
            "The rise between 09:00 and 10:00 is 4.",
            "The top value is 24 at 11:00.",
        ),
        (
            "1 h 20 min = 4/3",
            "v = 84 / (4/3) = 63",
        ),
        "Every number is right but no unit is written anywhere on the page.",
    ),
    _partial(
        "ximena-alcala",
        "Ximena Alcala",
        "dark_blue",
        30,
        _CORRECT_FACTORING,
        _CORRECT_GRAPH,
        (
            "1 h 20 min = 4/3 h",
            "v = 84 * 3/4 = 61 km/h",
        ),
        "Correct method, arithmetic slip: writes 84 * 3/4 = 61 instead of 63.",
    ),
    _partial(
        "delfina-arriaga",
        "Delfina Arriaga",
        "blue",
        31,
        (
            f"{STRIKE_PREFIX}x^2 + 5x + 6 = (x + 1)(x + 6)",
            "no, redo: x^2 + 5x + 6 = (x + 2)(x + 3)",
            "2 * 3 = 6 and 2 + 3 = 5. Expanding gives x^2 + 5x + 6.",
        ),
        _CORRECT_GRAPH,
        _CORRECT_WORD,
        "First factor attempt crossed out on the page, then a correct redo.",
    ),
)
