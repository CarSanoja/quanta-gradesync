from sample_batch.profiles import StudentProfile, demo_profile

FRACTION_PROFILES: tuple[StudentProfile, ...] = (
    demo_profile(
        "mariana-vasquez",
        "Mariana Vasquez",
        "blue",
        30,
        (
            "x^2 + 5x + 6 = (x + 2)(x + 3)",
            "I need two numbers with product 6 and sum 5, so 2 and 3.",
            "Check: (x + 2)(x + 3) = x^2 + 3x + 2x + 6 = x^2 + 5x + 6.",
        ),
        (
            "Between 09:00 and 10:00 the temperature climbs from 18 C to 22 C, so it gains 4 C.",
            "The maximum is 24 C at 11:00.",
        ),
        (
            "1 h 20 min = 1 + 20/60 h = 4/3 h",
            "v = 84 km / (4/3 h) = 84 * 3/4 = 63 km/h",
            "The bus averages 63 km/h.",
        ),
        notes="Correct; fraction conversion, expansion check, maximum with its time.",
    ),
    demo_profile(
        "joaquin-benitez",
        "Joaquin Benitez",
        "black",
        33,
        (
            "(x + 2)(x + 3)",
            "Product of the constants 6, sum 5. The pair (2, 3) is the only one that works.",
            "Substituting x = 1: (3)(4) = 12 and 1 + 5 + 6 = 12, so the factors hold.",
        ),
        (
            "09:00 -> 18 C, 10:00 -> 22 C. Increase of 4 C in one hour.",
            "Highest point of the curve: 24 C, reached at 11:00.",
        ),
        (
            "t = 1 h 20 min = 4/3 h",
            "v = d/t = 84 / (4/3) = 63 km/h",
        ),
        notes="Correct; verifies by substitution instead of expansion, largest handwriting.",
    ),
    demo_profile(
        "luciana-espinoza",
        "Luciana Espinoza",
        "dark_blue",
        28,
        (
            "x^2 + 5x + 6 factors as (x + 2)(x + 3)",
            "The factor pairs of 6 are 1 x 6 and 2 x 3; only 2 + 3 gives 5.",
            "Verified by expanding back to x^2 + 5x + 6.",
        ),
        (
            "The line rises 4 degrees Celsius over that hour, from 18 C to 22 C.",
            "Maximum: 24 C.",
        ),
        (
            "1 h 20 min = 4/3 of an hour",
            "84 : (4/3) = 84 x 3/4 = 63",
            "Average speed = 63 km/h",
        ),
        notes="Correct; states the maximum without its time.",
    ),
    demo_profile(
        "emiliano-castaneda",
        "Emiliano Castaneda",
        "graphite",
        32,
        (
            "x^2 + 5x + 6 = (x + 2)(x + 3)",
            "Roots are -2 and -3: their sum is -5 and their product is 6.",
            "That matches the coefficients, so the factors are right.",
        ),
        (
            "From nine to ten o'clock it warms up by 4 C, going 18 C -> 22 C.",
            "It peaks at 24 C around 11:00 and then falls.",
        ),
        (
            "1 h 20 min = 4/3 h",
            "v = 84 / (4/3) = 63 km/h",
            "63 km/h is a sensible average for a school route.",
        ),
        notes="Correct; argues from the roots rather than the factor pair.",
    ),
    demo_profile(
        "antonella-guerrero",
        "Antonella Guerrero",
        "blue",
        26,
        (
            "= (x + 2)(x + 3)",
            "2 * 3 = 6 and 2 + 3 = 5.",
            "Check by expansion: x^2 + 3x + 2x + 6 = x^2 + 5x + 6.",
        ),
        (
            "Rise of 4 C between 09:00 and 10:00, from 18 to 22 degrees.",
            "Max = 24 C at 11 h.",
        ),
        (
            "1 h 20 min = 1 1/3 h = 4/3 h",
            "v = 84 / (4/3) = 63 km/h",
        ),
        notes="Correct; terse mixed-number notation, smallest handwriting.",
    ),
    demo_profile(
        "facundo-alvarado",
        "Facundo Alvarado",
        "dark_blue",
        34,
        (
            "x^2 + 5x + 6 = (x + 3)(x + 2)",
            "I tried 1 and 6 first: 1 + 6 = 7, not 5. Then 2 and 3: 2 + 3 = 5.",
            "Expanding (x + 3)(x + 2) gives x^2 + 2x + 3x + 6 = x^2 + 5x + 6.",
        ),
        (
            "18 C at 09:00 and 22 C at 10:00, so +4 C.",
            "The maximum of the graph is 24 C at 11:00.",
        ),
        (
            "1 h 20 min = 4/3 h",
            "v = 84 * 3 / 4 = 63",
            "so 63 km/h",
        ),
        notes="Correct; factors written in the reverse order and a discarded first pair.",
    ),
    demo_profile(
        "paulina-cordoba",
        "Paulina Cordoba",
        "black",
        29,
        (
            "x^2+5x+6 = (x+2)(x+3)",
            "Sum 5, product 6 -> 2 and 3.",
            "Check: expand -> x^2 + 5x + 6. Correct.",
        ),
        (
            "The temperature goes from 18 C up to 22 C between 09:00 and 10:00, "
            "an increase of 4 C.",
            "The maximum reading is 24 C, at 11:00.",
        ),
        (
            "84 km in 1 h 20 min. 1 h 20 min = 4/3 h.",
            "v = 84 / (4/3) = 63 km/h",
            "The bus keeps an average of 63 km/h.",
        ),
        notes="Correct; compressed notation without spaces around the operators.",
    ),
    demo_profile(
        "matias-zambrano",
        "Matias Zambrano",
        "graphite",
        31,
        (
            "(x + 2)(x + 3) = x^2 + 5x + 6",
            "Two numbers that multiply to 6 and add to 5: 2, 3.",
            "Check term by term: x*x + x*3 + 2*x + 2*3 = x^2 + 5x + 6.",
        ),
        (
            "Change 09:00-10:00: +4 C, from 18 C to 22 C.",
            "Maximum 24 C at 11:00.",
        ),
        (
            "1 h 20 min = 4/3 h",
            "v = 84 / (4/3)",
            "v = 63 km/h",
        ),
        notes="Correct; telegraphic style with the check written term by term.",
    ),
)
