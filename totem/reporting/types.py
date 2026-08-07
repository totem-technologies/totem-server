from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class ReportFilters:
    session_slugs: tuple[str, ...] = ()
    space_slugs: tuple[str, ...] = ()
    keeper_slugs: tuple[str, ...] = ()
    category_slugs: tuple[str, ...] = ()

    def description(self) -> str:
        selections = (
            ("sessions", self.session_slugs),
            ("spaces", self.space_slugs),
            ("keepers", self.keeper_slugs),
            ("categories", self.category_slugs),
        )
        parts = [f"{name}={','.join(slugs)}" for name, slugs in selections if slugs]
        return ";".join(parts) if parts else "all"


@dataclass(frozen=True)
class SessionFact:
    session_slug: str
    space_slug: str
    keeper_slug: str
    scheduled_start: datetime
    scheduled_end: datetime
    seats: int
    cancelled: bool
    keeper_joined: bool
    beneficiary_rsvp_ids: frozenset[int]
    beneficiary_attendance_ids: frozenset[int]
    feedback_respondent_ids: frozenset[int]
    positive_feedback_respondent_ids: frozenset[int]


@dataclass(frozen=True)
class MetricResult:
    metric_name: str
    value: int | Decimal | None
    unit: str
    numerator: int | None
    denominator: int | None
    period_start: datetime
    period_end: datetime
    reporting_timezone: str
    period_kind: str
    period_label: str
    cohort: str
    generated_at: datetime
    definition_version: str
