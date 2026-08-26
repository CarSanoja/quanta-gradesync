from sample_batch.profiles import StudentProfile, demo_profile

DECIMAL_PROFILES: tuple[StudentProfile, ...] = (
    demo_profile(
        "valeria-montenegro",
        "Valeria Montenegro",
        "blue",
        30,
        (
            "x^2 + 5x + 6 = (x + 2)(x + 3)",
            "Because 2 x 3 = 6 and 2 + 3 = 5.",
            "Check: (x + 2)(x + 3) = x^2 + 5x + 6.",
        ),
        (
            "The temperature rises 4 C between 09:00 and 10:00, from 18 C to 22 C.",
            "The maximum is 24 C at 11:00.",
        ),
        (
            "1 h 20 min = 1 + 20/60 = 1.333 h",
            "v = 84 / 1.333 = 63 km/h",
            "Average speed 63 km/h.",
        ),
        notes="Correct; decimal conversion with the repeating value truncated.",
    ),
    demo_profile(
        "thiago-salazar",
        "Thiago Salazar",
        "black",
        32,
        (
            "x^2 + 5x + 6 = (x + 2)(x + 3)",
            "Looked for the pair with product 6 and sum 5.",
            "Verified: expanding gives back the original trinomial.",
        ),
        (
            "Between 09:00 and 10:00 it rises by 4 C, 18 C to 22 C.",
            "The highest temperature is 24 C.",
        ),
        (
            "1 h 20 min = 1.33 h, since 20/60 = 0.33",
            "v = 84 / 1.33 = 63 km/h approximately",
            "So about 63 km/h.",
        ),
        notes="Correct; rounds the conversion and hedges the final value.",
    ),
    demo_profile(
        "martina-cabrera",
        "Martina Cabrera",
        "dark_blue",
        28,
        (
            "(x + 2)(x + 3)",
            "Constants: 2 and 3 because 2 * 3 = 6 and 2 + 3 = 5.",
            "Substitution check: x = 0 gives 6 = 6 and x = 1 gives 12 = 12.",
        ),
        (
            "09:00: 18 C. 10:00: 22 C. Difference +4 C.",
            "Maximum 24 C at 11:00, then it cools.",
        ),
        (
            "1 h 20 min = 1.3333 h",
            "84 / 1.3333 = 63",
            "v = 63 km/h",
        ),
        notes="Correct; two substitution checks and a tabular graph reading.",
    ),
    demo_profile(
        "benjamin-arteaga",
        "Benjamin Arteaga",
        "graphite",
        33,
        (
            "x^2 + 5x + 6 = (x + 2)(x + 3)",
            "The roots of the trinomial are x = -2 and x = -3.",
            "Product of roots 6, sum of roots -5, which matches the coefficients.",
        ),
        (
            "It warms by 4 degrees Celsius in that hour.",
            "Peak value on the graph: 24 C at 11:00.",
        ),
        (
            "1 h 20 min = 1.333... h",
            "v = 84 km / 1.333 h = 63 km/h",
            "63 km/h on average for the whole trip.",
        ),
        notes="Correct; keeps the repeating decimal notation.",
    ),
    demo_profile(
        "catalina-jaramillo",
        "Catalina Jaramillo",
        "blue",
        29,
        (
            "x^2 + 5x + 6 = (x + 2)(x + 3)",
            "Factor pairs of 6: (1, 6) and (2, 3). Only (2, 3) adds to 5.",
            "Expansion check: x^2 + 3x + 2x + 6 = x^2 + 5x + 6.",
        ),
        (
            "From 09:00 to 10:00 the temperature increases 4 C, 18 C -> 22 C.",
            "Maximum: 24 C at 11:00.",
        ),
        (
            "1 h 20 min = 1.33 h",
            "v = 84 / 1.33 = 63 km/h",
            "The result is reasonable for a bus on a city route.",
        ),
        notes="Correct; enumerates the factor pairs before choosing.",
    ),
    demo_profile(
        "josefina-peralta",
        "Josefina Peralta",
        "black",
        26,
        (
            "x^2 + 5x + 6 = (x + 2)(x + 3)",
            "I need a + b = 5 and a * b = 6, so a = 2 and b = 3.",
            "Check: (x + 2)(x + 3) expands to x^2 + 5x + 6.",
        ),
        (
            "The graph climbs from 18 C to 22 C between 09:00 and 10:00: a rise of 4 C.",
            "The maximum temperature of the classroom is 24 C, reached at 11:00.",
        ),
        (
            "1 h 20 min = 1.333 h",
            "v = d / t = 84 / 1.333",
            "v = 63 km/h",
        ),
        notes="Correct; introduces symbols a and b before solving.",
    ),
    demo_profile(
        "alejandro-solorzano",
        "Alejandro Solorzano",
        "graphite",
        34,
        (
            "x^2 + 5x + 6 = (x + 2)(x + 3)",
            "Product 6, sum 5 -> the pair is 2 and 3.",
            "Expanded again to be sure: x^2 + 5x + 6.",
        ),
        (
            "Between 09:00 and 10:00 the temperature goes up 4 C.",
            "Highest point 24 C at 11:00.",
        ),
        (
            "1 h 20 min = 1.33 h",
            "84 / 1.33 = 63 km/h",
            "Answer: 63 km/h",
        ),
        notes="Correct; largest handwriting, answer boxed off on its own line.",
    ),
)
