from dataclasses import dataclass

SUBJECT = "Matematicas"
GRADE_LEVEL = "10"
ASSESSMENT = "Parcial1"
YEAR = 2026

ROSTER_REFERENCE = "reference"
ROSTER_DEMO = "demo"
# The three sections one teacher carries through a single week.
ROSTER_SECTION_A = "section-10a"
ROSTER_SECTION_B = "section-10b"
ROSTER_SECTION_C = "section-10c"
SECTION_ROSTERS: tuple[str, ...] = (ROSTER_SECTION_A, ROSTER_SECTION_B, ROSTER_SECTION_C)
# A second sitting, so the three sections never collide with the acceptance
# fixture or the single-batch demo, which both use Parcial1.
SECTION_ASSESSMENT = "Parcial2"


@dataclass(frozen=True)
class LotSpec:
    roster: str
    class_id: str
    job_id: str
    header_date: str
    triggered_at: str
    trace_id: str
    message_id: str
    assessment: str = ASSESSMENT

    @property
    def lot_code(self) -> str:
        return f"{YEAR}_{SUBJECT}_{self.class_id}_{self.assessment}"

    @property
    def batch_prefix(self) -> str:
        return f"batches/{self.lot_code}"

    @property
    def header_line(self) -> str:
        sitting = "Parcial 2" if self.assessment == SECTION_ASSESSMENT else "Parcial 1"
        return (
            f"Mathematics  |  Grade {self.class_id}  |  {sitting}  |  {self.header_date}"
        )


REFERENCE_LOT = LotSpec(
    roster=ROSTER_REFERENCE,
    class_id="10A",
    job_id="sample-2026-matematicas-10a-parcial1",
    header_date="19 August 2026",
    triggered_at="2026-08-19T13:00:00+00:00",
    trace_id="5a1c9f24b7e30d18",
    message_id="sample-batch-message-1",
)

DEMO_LOT = LotSpec(
    roster=ROSTER_DEMO,
    class_id="10B",
    job_id="demo-2026-matematicas-10b-parcial1",
    header_date="25 August 2026",
    triggered_at="2026-08-25T13:00:00+00:00",
    trace_id="c47b13d9e6a08f52",
    message_id="demo-batch-message-1",
)

# Same paper, same day, three sittings — the order the teacher walks them in.
SECTION_LOTS: dict[str, LotSpec] = {
    ROSTER_SECTION_A: LotSpec(
        roster=ROSTER_SECTION_A,
        class_id="10A",
        job_id="sections-2026-matematicas-10a-parcial2",
        header_date="28 August 2026",
        triggered_at="2026-08-28T12:40:00+00:00",
        trace_id="9f2ab6c1d47e0538",
        message_id="section-10a-message-1",
        assessment=SECTION_ASSESSMENT,
    ),
    ROSTER_SECTION_B: LotSpec(
        roster=ROSTER_SECTION_B,
        class_id="10B",
        job_id="sections-2026-matematicas-10b-parcial2",
        header_date="28 August 2026",
        triggered_at="2026-08-28T12:55:00+00:00",
        trace_id="3c80d5e29ab14f76",
        message_id="section-10b-message-1",
        assessment=SECTION_ASSESSMENT,
    ),
    ROSTER_SECTION_C: LotSpec(
        roster=ROSTER_SECTION_C,
        class_id="10C",
        job_id="sections-2026-matematicas-10c-parcial2",
        header_date="28 August 2026",
        triggered_at="2026-08-28T13:10:00+00:00",
        trace_id="7e415b9d0c28a3f2",
        message_id="section-10c-message-1",
        assessment=SECTION_ASSESSMENT,
    ),
}

LOTS: dict[str, LotSpec] = {
    ROSTER_REFERENCE: REFERENCE_LOT,
    ROSTER_DEMO: DEMO_LOT,
    **SECTION_LOTS,
}
