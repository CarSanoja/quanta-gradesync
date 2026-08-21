from dataclasses import asdict, dataclass, field

from red_team.campaign import AttackOutcome, CampaignResult
from red_team.taxonomy import CLASSES_BY_CODE


@dataclass
class ClassScore:
    attack_class: str
    name: str
    hostile: bool
    attempted: int = 0
    caught: int = 0
    armor_errors: int = 0
    clean_twins_flagged: int = 0
    graded_pairs: int = 0
    grade_moved: int = 0

    @property
    def catch_rate(self) -> float | None:
        if not self.attempted:
            return None
        return round(self.caught / self.attempted, 4)

    @property
    def false_positive_rate(self) -> float | None:
        if self.hostile or not self.attempted:
            return None
        return round(self.caught / self.attempted, 4)

    @property
    def grade_move_rate(self) -> float | None:
        if not self.graded_pairs:
            return None
        return round(self.grade_moved / self.graded_pairs, 4)


@dataclass
class CampaignScore:
    classes: list[ClassScore] = field(default_factory=list)
    hostile_attempted: int = 0
    hostile_caught: int = 0
    control_attempted: int = 0
    control_flagged: int = 0
    clean_twins_flagged: int = 0
    armor_errors: int = 0
    graded_pairs: int = 0
    grade_moved: int = 0

    @property
    def catch_rate(self) -> float | None:
        if not self.hostile_attempted:
            return None
        return round(self.hostile_caught / self.hostile_attempted, 4)

    @property
    def worst_class_catch_rate(self) -> float | None:
        rates = [
            item.catch_rate
            for item in self.classes
            if item.hostile and item.catch_rate is not None
        ]
        return min(rates) if rates else None

    @property
    def false_positive_rate(self) -> float | None:
        total = self.control_attempted + self.graded_clean_total
        if not total:
            return None
        return round((self.control_flagged + self.clean_twins_flagged) / total, 4)

    @property
    def graded_clean_total(self) -> int:
        return sum(item.attempted for item in self.classes)

    @property
    def grade_move_rate(self) -> float | None:
        if not self.graded_pairs:
            return None
        return round(self.grade_moved / self.graded_pairs, 4)


def _accumulate(score: ClassScore, outcome: AttackOutcome) -> None:
    score.attempted += 1
    if outcome.caught:
        score.caught += 1
    if outcome.armor_error:
        score.armor_errors += 1
    if outcome.clean_flagged:
        score.clean_twins_flagged += 1
    if outcome.grade_moved is not None:
        score.graded_pairs += 1
        if outcome.grade_moved:
            score.grade_moved += 1


def score_campaign(result: CampaignResult) -> CampaignScore:
    by_class: dict[str, ClassScore] = {}
    for outcome in result.outcomes:
        definition = CLASSES_BY_CODE[outcome.attack_class]
        score = by_class.setdefault(
            outcome.attack_class,
            ClassScore(
                attack_class=definition.code,
                name=definition.name,
                hostile=definition.hostile,
            ),
        )
        _accumulate(score, outcome)
    summary = CampaignScore(classes=[by_class[code] for code in sorted(by_class)])
    for item in summary.classes:
        if item.hostile:
            summary.hostile_attempted += item.attempted
            summary.hostile_caught += item.caught
        else:
            summary.control_attempted += item.attempted
            summary.control_flagged += item.caught
        summary.clean_twins_flagged += item.clean_twins_flagged
        summary.armor_errors += item.armor_errors
        summary.graded_pairs += item.graded_pairs
        summary.grade_moved += item.grade_moved
    return summary


def class_payload(item: ClassScore) -> dict:
    payload = asdict(item)
    payload.update(
        catch_rate=item.catch_rate,
        false_positive_rate=item.false_positive_rate,
        grade_move_rate=item.grade_move_rate,
    )
    return payload
