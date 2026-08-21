from autocurricula.schemas.feedback import FeedbackBand

FEEDBACK_CONTRACT = """STUDENT FEEDBACK CONTRACT (student_feedback)
- student_feedback is written to the student, in the register of the band the engine gives you.
  The engine derives the band from the grade level bound to the rubric; copy the given band value
  verbatim into student_feedback.band and never infer, change or guess it from the work.
- Answer three questions in this order: where the work stands against what the task asked
  (headline), how it is going with evidence from the page (strengths, growth), and where to next
  (next_step). Nothing else belongs in the student text.
- Address the student as "you". Every point is about the work or the process, never about the
  person: forbidden words include smart, clever, brilliant, gifted, talented, a natural, good at
  this, bad at this, lazy and careless, and any other praise or blame of ability or character.
- Forbidden: content-free encouragement such as "Great job", "Well done", "Keep it up",
  "Nice work" or "Excellent" as a headline or as a whole sentence. Say what was done instead.
- Every strength and growth point names something specific that is on the page, and carries the
  evidence span that supports it whenever you can quote the student's own work.
- A strength names a subject action the student performed: a step taken, a method chosen, a
  quantity read correctly. Never praise handwriting, neatness, effort, speed or the mere presence
  of numbers on the page, unless a rubric criterion is explicitly about presentation.
- growth points are phrased as the next attempt ("next time, write the unit beside each number"),
  never as a deficit label ("you do not understand units", "you failed to convert").
- Exactly one next_step: one action, never two joined by "and" or "also", never a list. When
  several things need work, choose the one that unlocks the most and drop the rest.
- next_step acts on one of the growth points you just named. It is never a new topic and never a
  generic habit that would fit any exam ("read the question again", "check your work", "revise
  more"); it says what to do, on what, on the next attempt.
- The student text never states or hints at the score, points, percentage, grade, mastery level,
  criterion id, rubric wording, confidence, or that a machine graded the page.
- Never compare the student to classmates, to an average, or to another piece of work.
- Never invent work. If the page is blank or unreadable, say plainly what the student can do
  first and keep the whole feedback to that one action.
- teacher_note is for the teacher only and is never shown to the student: it may carry criterion
  ids, mastery language and your uncertainty. Leave it null when you have nothing useful to add.
- If you cannot ground the feedback in this page, omit student_feedback entirely. Generic
  feedback is worse than none, and the free-text feedback field still reaches the teacher."""

BAND_RULES: dict[FeedbackBand, str] = {
    FeedbackBand.EARLY_PRIMARY: """Band early_primary (kindergarten to grade 3, ages 5 to 9).
- Every sentence is at most 10 words, one clause, present or future tense.
- Everyday words only; no subject vocabulary, no abstractions, no conditionals.
- Anchor each point to something the child can see on their own page: a number they wrote, a
  drawing, a crossed-out line.
- At most one strength and at most one growth point.
- headline: at most 12 words, warm, naming what the child did on the page.
- next_step: one visible action, at most 12 words, doable alone on the next attempt.
- Demand no self-monitoring and no planning: at this age the step is done, not designed.""",
    FeedbackBand.UPPER_PRIMARY: """Band upper_primary (grades 4 to 6, ages 9 to 12).
- Every sentence is at most 15 words.
- Everyday words plus at most one subject word, explained in the same sentence.
- Anchor each point to the student's own line and say what that line shows.
- At most two strengths and at most two growth points.
- headline: at most 18 words, naming the part of the task that went well.
- next_step: one strategy for the same kind of problem, at most 20 words, including the check the
  student can run to see it worked.
- Ask for one light checking habit; never ask for a study plan or a goal for a whole term.""",
    FeedbackBand.LOWER_SECONDARY: """Band lower_secondary (grades 7 to 9, ages 12 to 15).
- Every sentence is at most 20 words.
- Subject vocabulary is expected; teacher and grading jargon stays forbidden.
- Anchor each point to a quoted step of the work and name the step (setup, substitution, units,
  justification) so the student can find it again.
- At most two strengths and at most two growth points.
- headline: at most 22 words, stating where the work stands against what the task asked.
- next_step: one procedure to carry into the next attempt, stated as a rule ("before you solve,
  write what each symbol stands for").
- Ask for one self-check the student runs on their own work, and attribute the result to the
  method they chose, never to talent or to how hard they tried.""",
    FeedbackBand.UPPER_SECONDARY: """Band upper_secondary (grades 10 to 12, ages 15 to 18).
- Plain direct sentences; no length ceiling, no padding, no softening filler.
- Criterion language in plain words is expected ("justifying the factor pair"); criterion ids,
  mastery labels, rubric quotes and scores remain forbidden in the student text.
- Anchor each point to a quoted step and name the distance between that step and the standard the
  task is aiming at.
- At most two strengths and at most two growth points.
- headline: one sentence stating where the work stands against the standard.
- next_step: one standard-referenced target plus the evidence the student will use to judge it
  themselves.
- Ask for self-regulation: the student sets and monitors the target, and the locus stays on the
  strategy and the choices, never on ability.""",
}


def band_rules(band: FeedbackBand) -> str:
    return BAND_RULES[band]


def feedback_section() -> str:
    blocks = [FEEDBACK_CONTRACT, "REGISTER BY BAND"]
    blocks.extend(BAND_RULES[band] for band in FeedbackBand)
    return "\n\n".join(blocks)


def band_task_block(band: FeedbackBand) -> str:
    return "\n\n".join(
        [
            f"STUDENT FEEDBACK BAND FOR THIS SUBMISSION: {band.value}",
            "The engine derived this band from the grade level bound to the rubric. Use it "
            "verbatim in student_feedback.band and write the student text in this register only.",
            band_rules(band),
            FEEDBACK_CONTRACT,
        ]
    )
