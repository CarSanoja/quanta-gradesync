# Developmental feedback bands — live evidence (2026-08-21)

One real exam page from the demo batch, graded live by the production grading
agent under four different grade levels so that all four feedback bands are
exercised. Everything quoted below is text `gemini-3.5-flash` actually produced
on Vertex; nothing is illustrative. Design and rationale:
[student-feedback](../architecture/student-feedback.md).

| Item | Value |
|---|---|
| Model | `gemini-3.5-flash`, Vertex AI, location `global`, thinking enabled |
| Agent path | `AdkGradingEvaluator.for_grade_level(...)` → the production `grade()`, page JPEG inline |
| Batch | `generate_sample_batch.py --seed 20260819`, lot `2026_Matematicas_10A_Parcial1` |
| Rubric | `mat-10a-parcial1` (factoring 4 pts, graph-reading 3 pts, word-problem 3 pts) |
| Pages | `camila-rios.jpg` (mixed work, human ground truth 7.5/10) and `tomas-vega.jpg` (weak work, ground truth 3.0/10) |
| Grade levels exercised | 2 → `early_primary`, 5 → `upper_primary`, 8 → `lower_secondary`, 11 → `upper_secondary` |
| Calls | 12 (1 schema smoke, 6 first pass, 5 after the prompt fix) |
| Spend | **$0.88** measured (75 763 + 6 759 input tokens, 79 113 + 5 183 output tokens at $1.50/$9.00 per Mtok) |
| Latency | 28–41 s per single-page grading call |

**The experiment holds the content constant and varies only the band.** The page
is real grade-10 mathematics in every run; the grade level bound to the rubric
is what changes. That isolates register as the single variable, and it is also
the honest limitation of the exercise: a real second-grader would never see this
page, so the `early_primary` runs show the register machinery working against
content it will never meet in production (see *What came out wrong*).

---

## 1. The register gradient, measured

Same page, same score (7.0/10 in all four runs), four bands:

| Band | headline words | next_step words | longest student-facing sentence | strengths | growth |
|---|---:|---:|---:|---:|---:|
| `early_primary` | 8 | 7 | 9 | 1 | 1 |
| `upper_primary` | 14 | 14 | 14 | 2 | 2 |
| `lower_secondary` | 18 | 18 | 19 | 2 | 2 |
| `upper_secondary` | 28 | 22 | 28 | 2 | 2 |

Every band respected its own ceiling (≤10, ≤15, ≤20, none) and its own point
budget (1+1 for early primary, ≤2+2 above it). The gradient is monotone across
all three measures without any word-count enforcement in code — it comes from
the band block alone.

## 2. What the engine wrote — `camila-rios`, one page, four bands

### early_primary (grade level 2)

**headline** — You have many correct numbers on your page.

**strength** — You write the correct number 63 for the bus. *(cited: `84 / (4/3) = 63 km/h`)*

**growth** — Next time, write the clock time next to 24. *(cited: `the max is 24`)*

**next_step** — Write the clock time next to 24.

**teacher_note** (never shown to the student) — The student demonstrated proficiency across all criteria. In 'factoring', she missed advanced status by not showing an algebraic multiplication check. In 'graph-reading', she missed stating the time (10:00) when the maximum temperature occurs. In 'word-problem', she did not include an interpretation sentence.

**flat `feedback` field** — Your calculations and factoring are correct; next step is to include the time when the maximum temperature occurs.

### upper_primary (grade level 5)

**headline** — Finding the correct numbers and calculating the speed went very well on this task.

**strength** — Your answer '(x + 2)(x + 3)' shows you found the correct numbers. *(cited: `x^2 + 5x + 6 = (x + 2)(x + 3)`)*

**strength** — Your work '84 / (4/3) = 63' shows you changed minutes to hours correctly. *(cited: `84 / (4/3) = 63 km/h`)*

**growth** — Next time, add the matching hour to your line 'the max is 24'. *(cited: `it goes up 4 degrees and the max is 24`)*

**growth** — Next time, write a final sentence explaining what '63 km/h' means. *(cited: `84 / (4/3) = 63 km/h`)*

**next_step** — Next time, write the hour beside the high temperature to check both are there.

**teacher_note** (never shown to the student) — The student demonstrated solid procedural skill in factoring, time conversion, and speed calculation. Missing points are due to incomplete graph reading (no time given for maximum) and lack of a final interpretation sentence for the speed. One quick reminder about fully answering all parts of graph/word problems should resolve this.

**flat `feedback` field** — Your factoring and time-to-hour conversions are accurate; next step is writing an interpretation sentence for the speed.

### lower_secondary (grade level 8)

**headline** — You found the correct solutions and conversions, but some justifications and details are missing from your final steps.

**strength** — For the justification step, you wrote "product 6 sum 5" to explain your choice of numbers. *(cited: `product 6 sum 5`)*

**strength** — In the setup step, you converted time to hours with "(4/3)" and calculated the speed. *(cited: `84 / (4/3) = 63 km/h`)*

**growth** — Next time, expand "(x + 2)(x + 3)" in the justification step to verify it equals the original quadratic. *(cited: `(x + 2)(x + 3)`)*

**growth** — Next time, add the time that the maximum temperature "24" occurs to complete the reading step. *(cited: `the max is 24`)*

**next_step** — Before submitting, use this rule: check that every graph value is paired with its time on the x-axis.

**teacher_note** (never shown to the student) — The student achieved proficient across all criteria. In factoring, they knew the sum and product method but omitted the written expansion. In the average speed problem, they set up the fraction division correctly but did not write a concluding sentence. For graph-reading, they omitted the time coordinate of the maximum.

**flat `feedback` field** — Your factoring and speed calculations are correct; next step is reporting the time for the maximum temperature.

### upper_secondary (grade level 11)

**headline** — Your work shows correct calculations and factors across all three tasks, but falls short of the full standards due to missing steps in your justifications and unit descriptions.

**strength** — You correctly factored the quadratic expression into binomials and identified the target product and sum, showing a clear grasp of the factoring method. *(cited: `x^2 + 5x + 6 = (x + 2)(x + 3)` / `product 6 sum 5`)*

**strength** — You correctly converted the time into hours as a fraction and calculated the correct average speed. *(cited: `84 / (4/3) = 63 km/h`)*

**growth** — To fully satisfy the standard for justifying your factor pair, your next attempt needs a written check demonstrating that expanding the binomials yields the original expression. *(cited: `x^2 + 5x + 6 = (x + 2)(x + 3)` / `product 6 sum 5`)*

**growth** — For the graph-reading task, the standard requires reporting the time the maximum occurs and attaching units to all reported numbers. *(cited: `it goes up 4 degrees and the max is 24`)*

**next_step** — On your next factoring task, verify your binomial factors by multiplying them out to check if they match the original quadratic trinomial.

**teacher_note** (never shown to the student) — The student has strong procedural skills across factoring, graph reading, and average speed calculations. However, they consistently omit formal justification steps (such as the algebraic check for factoring, unit conversion steps for speed, and units/time details for the graph maximum). Addressing these notation and verification gaps will help them reach advanced mastery.

**flat `feedback` field** — Your calculations for factoring and average speed are correct; next, include written algebraic checks and units for your final graph readings.

## 3. A weak page — `tomas-vega`, ground truth 3.0/10

The interesting question on a failing page is whether the register survives
contact with bad work, or collapses into a deficit report.

### early_primary (grade level 2)

**headline** — You show your math work clearly on this page.

**strength** — Your number 22 C shows the highest temperature. *(cited: `The maximum is 22 C.`)*

**growth** — Next time, you will add the two numbers. *(cited: `1 * 6 = 6, so the factors work.`)*

**next_step** — Add your two numbers to find the middle number.

**teacher_note** (never shown to the student) — Tomas successfully sets up the speed ratio and extracts a graph's maximum with units. However, he treats 20 minutes as 0.2 hours and only verifies the product of his factors (1 * 6 = 6) while ignoring the middle term's sum (1 + 6 = 7 instead of 5). Targeted intervention on decimal conversions of time and a two-step check for trinomial factoring (product and sum) will help.

### upper_secondary (grade level 11), first pass

**headline** — Your work demonstrates a clear understanding of problem-solving setups and reading general trends, but it falls short of the standard in algebraic precision and accurate unit conversions.

**strength** — You successfully located the maximum value on the graph and recorded it with its units. *(cited: `The maximum is 22 C.`)*

**strength** — In the word problem, you correctly set up the formula for average speed as the ratio of distance over time. *(cited: `v = 84 / 1.2 = 70 km/h`)*

**growth** — Next time, verify both the product and the sum of your chosen factor pair to ensure they expand back to the original trinomial, rather than checking only the product. *(cited: `1 * 6 = 6, so the factors work.`)*

**growth** — Next time, convert minutes to hours by dividing by 60 to find the precise decimal value, rather than treating minutes as a direct decimal fraction of an hour. *(cited: `1 h 20 min = 1.2 h`)*

**next_step** — Before submitting your next math set, expand your factored quadratic expressions completely using the distributive property to verify that your resulting polynomial matches the original prompt exactly.

Assessed against the criteria: no deficit labels, no ability attribution, both
gaps stated as the next attempt with the student's own line cited, and the
diagnostic ("treats 20 minutes as 0.2 hours") kept in `teacher_note` where the
teacher can act on it. This is what the change was for — a 40 % page that reads
as two concrete moves rather than as a verdict.

## 4. What came out wrong — first pass, and what it forced

The first live pass exposed three defects that the offline tests could not see.
All three were fixed in the prompt and re-run; both passes are quoted here
because the failures are the useful part.

**(a) The band ceiling pushed the model to praise surface features.**
At `early_primary` on grade-10 content, the first pass produced:

> **strength** — You write the number 63 on your page.
> **headline** — You write neat numbers and letters on your page. *(tomas-vega)*

Praise of penmanship is exactly the person-adjacent, content-free feedback the
design set out to eliminate — the model retreated to whatever it could say in
ten everyday words. **Fix:** the contract now requires a strength to name a
subject action (a step taken, a method chosen, a quantity read correctly) and
forbids praising handwriting, neatness, effort or speed. After the fix the same
page yielded *"Your number 22 C shows the highest temperature."*

**(b) `next_step` did not follow from the growth points.**
First pass at `upper_primary`: two growth points about the time of the maximum
and a missing interpretation sentence, then

> **next_step** — Multiply your answer out to check if it matches the starting question exactly.

— a third topic, so the feed-forward pointed away from the gap that had just
been named. At `lower_secondary` it degraded further into a compliance habit
(*"read the prompt to check that you included every detail"*). **Fix:** the
contract now requires `next_step` to act on one of the growth points and
explicitly forbids generic habits that would fit any exam. After the fix all
four bands point at a named gap.

**(c) The flat `feedback` string turned into a form.**
Three first-pass runs emitted *"Strength: ... Next step: ..."* with literal
labels, a regression caused by my own wording in the OUTPUT block. **Fix:** the
instruction now asks for one sentence of plain prose with no labels. All five
post-fix runs comply.

## 5. What is still wrong, after the fix

- **The headline is the weak field at `early_primary`.** *"You have many correct
  numbers on your page."* and *"You show your math work clearly on this page."*
  still describe the surface. The strength rule does not cover the headline, and
  on content far above the band there is little else the model can compress into
  nine words. Extending the subject-action requirement to the headline is the
  obvious next change; it was left out of this cycle so that the fix and the
  measurement stay separable.
- **`early_primary` next_step can restate the growth point verbatim.** *"Write
  the clock time next to 24."* appears as both. Harmless, arguably good for a
  seven-year-old, but it means the two fields carry one idea instead of two.
- **`lower_secondary` remains the flattest band.** Its next_step is still framed
  as a submission-time rule (*"Before submitting, use this rule: check that
  every graph value is paired with its time"*) rather than as mathematics. The
  band asks for a self-check and a procedure at once, and the model merges them.
- **Growth phrasing at `early_primary` drifts into the future tense** — *"Next
  time, you will add the two numbers"* — which reads as a prediction rather than
  an instruction, and *"the two numbers"* is under-specified until the next_step
  disambiguates it.
- **Redundancy with the criterion comments.** The rubric comments and the
  student feedback frequently say the same thing in two registers. That is by
  design (one is for the teacher's record, one for the student), but it doubles
  the output tokens: these runs cost 6–8 k output tokens each against ~7 k
  input.

## 6. Grading was not disturbed

The band block is appended to the same call that produces the scores, so the
obvious risk is that it moves the grade. It did not, in this sample:
`camila-rios` scored **7.0/10 in all eight runs** (four bands × two passes), and
`tomas-vega` scored 4.5, 4.0 and 4.5 across three runs — inside the
one-mastery-bucket variance already reported in
[calibration-2026-08-20](calibration-2026-08-20.md). Human ground truth is 7.5
and 3.0 respectively, unchanged from the baseline measured before this change.

## 7. Reproducing this

```python
settings = Settings(local_mode=False, gcp_project_id="quanta-gradesync")
configure_genai_env(settings)
evaluator = AdkGradingEvaluator(settings).for_grade_level("5")
result = await evaluator.grade(submission, rubric, retrieved_context)
result.student_feedback.band   # FeedbackBand.UPPER_PRIMARY, stamped by the engine
```

The band is never asked of the model: `for_grade_level` derives it with
`band_for_grade_level`, injects that band's rules into the call, and overwrites
whatever band the model wrote back. An unparseable grade level yields no band,
and no band means `student_feedback is None` — the flat `feedback` string still
ships.
