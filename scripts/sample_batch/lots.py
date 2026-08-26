from dataclasses import dataclass

SUBJECT = "Matematicas"
GRADE_LEVEL = "10"
ASSESSMENT = "Parcial1"
YEAR = 2026

ROSTER_REFERENCE = "reference"
ROSTER_DEMO = "demo"


@dataclass(frozen=True)
class LotSpec:
    roster: str
    class_id: str
    job_id: str
    header_date: str
    triggered_at: str
    trace_id: str
    message_id: str

    @property
    def lot_code(self) -> str:
        return f"{YEAR}_{SUBJECT}_{self.class_id}_{ASSESSMENT}"

    @property
    def batch_prefix(self) -> str:
        return f"batches/{self.lot_code}"

    @property
    def header_line(self) -> str:
        return (
            f"Mathematics  |  Grade {self.class_id}  |  Parcial 1  |  {self.header_date}"
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

LOTS: dict[str, LotSpec] = {
    ROSTER_REFERENCE: REFERENCE_LOT,
    ROSTER_DEMO: DEMO_LOT,
}
