from sample_batch.profiles import QUALITY_POOR, StudentProfile, demo_profile

POOR_PROFILES: tuple[StudentProfile, ...] = (
    demo_profile(
        "nahuel-riquelme",
        "Nahuel Riquelme",
        "blue",
        31,
        (
            "x^2 + 5x + 6 = (x + 5)(x + 6)",
            "5 and 6 are the numbers that appear in the problem.",
        ),
        ("The temperature stays the same all morning.",),
        ("84 km in 1 h 20 min, so about 84 km/h.",),
        quality=QUALITY_POOR,
        notes="Copies the coefficients into the factors, misreads the graph, no conversion.",
    ),
    demo_profile(
        "maximiliano-duarte",
        "Maximiliano Duarte",
        "black",
        33,
        (
            "x^2 + 5x + 6 = (x + 6)(x - 1)",
            "6 - 1 = 5.",
        ),
        ("It goes down from 09:00 to 10:00 and the minimum is 18 C.",),
        ("v = 84 x 1.20 = 100.8 km/h",),
        quality=QUALITY_POOR,
        notes="Wrong on all three items: sign error, inverted trend, multiplies by the time.",
    ),
)
