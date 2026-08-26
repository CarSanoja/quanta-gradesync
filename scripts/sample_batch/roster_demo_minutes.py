from sample_batch.profiles import StudentProfile, demo_profile

MINUTE_PROFILES: tuple[StudentProfile, ...] = (
    demo_profile(
        "florencia-bustos",
        "Florencia Bustos",
        "blue",
        30,
        (
            "x^2 + 5x + 6 = (x + 2)(x + 3)",
            "2 and 3: product 6, sum 5.",
            "Check by expansion: x^2 + 3x + 2x + 6 = x^2 + 5x + 6.",
        ),
        (
            "18 C at 09:00, 22 C at 10:00: the temperature gains 4 C.",
            "Maximum 24 C at 11:00.",
        ),
        (
            "1 h 20 min = 80 min = 80/60 h = 4/3 h",
            "v = 84 / (4/3) = 63 km/h",
            "The bus averages 63 km/h.",
        ),
        notes="Correct; converts through 80 minutes before reaching the fraction.",
    ),
    demo_profile(
        "ignacio-carvajal",
        "Ignacio Carvajal",
        "black",
        32,
        (
            "(x + 2)(x + 3)",
            "Because 2 * 3 = 6 and 2 + 3 = 5, these are the right factors.",
            "Verified by multiplying the two binomials back out.",
        ),
        (
            "It rises 4 C over that hour.",
            "Maximum: 24 C at 11:00.",
        ),
        (
            "The trip lasts 80 minutes.",
            "84 km / 80 min = 1.05 km/min",
            "1.05 * 60 = 63 km/h",
        ),
        notes="Correct; solves per minute and scales up to the hour.",
    ),
    demo_profile(
        "amparo-linares",
        "Amparo Linares",
        "dark_blue",
        28,
        (
            "x^2 + 5x + 6 = (x + 2)(x + 3)",
            "Roots -2 and -3 give the factors.",
            "Check: sum of roots -5 matches the 5x term, product 6 matches the constant.",
        ),
        (
            "Between 09:00 and 10:00 the classroom warms from 18 C to 22 C: +4 C.",
            "The maximum is 24 C.",
        ),
        (
            "1 h 20 min = 80 min",
            "80 min = 4/3 h",
            "v = 84 / (4/3) = 63 km/h",
        ),
        notes="Correct; states the maximum without its time, one step per line.",
    ),
    demo_profile(
        "bruno-maldonado",
        "Bruno Maldonado",
        "graphite",
        33,
        (
            "x^2 + 5x + 6 = (x + 2)(x + 3)",
            "Tried (1, 6): sum 7, no. Tried (2, 3): sum 5, yes.",
            "Expansion confirms it.",
        ),
        (
            "+4 C between the two hours, from 18 C to 22 C.",
            "It peaks at 24 C at 11:00 and then goes down.",
        ),
        (
            "80 minutes in total.",
            "In one minute the bus does 84/80 = 1.05 km.",
            "In one hour: 1.05 x 60 = 63 km, so 63 km/h.",
        ),
        notes="Correct; unit-rate reasoning written out in prose.",
    ),
    demo_profile(
        "regina-ocampo",
        "Regina Ocampo",
        "blue",
        29,
        (
            "(x + 2)(x + 3) = x^2 + 5x + 6",
            "The two numbers are 2 and 3.",
            "Check: 2 x 3 = 6 and 2 + 3 = 5, and expanding gives the trinomial back.",
        ),
        (
            "The temperature increases by 4 C between 09:00 and 10:00.",
            "Maximum reading: 24 C at 11:00.",
        ),
        (
            "1 h 20 min = 80 min = 4/3 h",
            "v = 84 * 3/4 = 63 km/h",
        ),
        notes="Correct; multiplies by the reciprocal instead of dividing.",
    ),
    demo_profile(
        "dario-esquivel",
        "Dario Esquivel",
        "black",
        31,
        (
            "x^2 + 5x + 6 = (x + 2)(x + 3)",
            "Numbers with product 6 and sum 5: 2 and 3.",
            "Substituting x = 2: (4)(5) = 20 and 4 + 10 + 6 = 20.",
        ),
        (
            "From 09:00 to 10:00: 18 C -> 22 C, a change of +4 C.",
            "Maximum 24 C at 11:00.",
        ),
        (
            "1 h 20 min = 80 min",
            "v = 84 km / (80/60 h) = 63 km/h",
            "63 km/h.",
        ),
        notes="Correct; checks the factorisation at x = 2.",
    ),
    demo_profile(
        "leonardo-pizarro",
        "Leonardo Pizarro",
        "graphite",
        30,
        (
            "x^2 + 5x + 6 = (x + 2)(x + 3)",
            "Product 6 and sum 5 forces the pair (2, 3).",
            "Expansion check: x^2 + 3x + 2x + 6 = x^2 + 5x + 6.",
        ),
        (
            "Between 09:00 and 10:00 the temperature goes up by 4 C.",
            "The curve reaches its maximum, 24 C, at 11:00.",
        ),
        (
            "1 h 20 min = 80 min = 80/60 = 4/3 h",
            "v = 84 : 4/3 = 63",
            "The bus averages 63 km/h over the 84 km.",
        ),
        notes="Correct; colon division sign and a closing interpretation sentence.",
    ),
)
