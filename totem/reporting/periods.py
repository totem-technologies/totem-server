from dataclasses import dataclass
from datetime import datetime
from datetime import timezone as dt_timezone
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class ReportPeriod:
    """A half-open reporting period expressed as UTC instants."""

    start: datetime
    end: datetime
    timezone: str
    kind: str
    label: str

    def __post_init__(self):
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError("Report period boundaries must be timezone-aware")
        if self.start >= self.end:
            raise ValueError("Report period start must be before its end")

    @classmethod
    def calendar_year(cls, year: int, timezone: str) -> "ReportPeriod":
        reporting_timezone = ZoneInfo(timezone)
        start = datetime(year, 1, 1, tzinfo=reporting_timezone)
        end = datetime(year + 1, 1, 1, tzinfo=reporting_timezone)
        return cls(
            start=start.astimezone(dt_timezone.utc),
            end=end.astimezone(dt_timezone.utc),
            timezone=timezone,
            kind="year",
            label=str(year),
        )

    @classmethod
    def calendar_quarter(cls, year: int, quarter: int, timezone: str) -> "ReportPeriod":
        if quarter not in range(1, 5):
            raise ValueError("Quarter must be between 1 and 4")

        reporting_timezone = ZoneInfo(timezone)
        start_month = (quarter - 1) * 3 + 1
        end_year = year + (1 if quarter == 4 else 0)
        end_month = 1 if quarter == 4 else start_month + 3
        start = datetime(year, start_month, 1, tzinfo=reporting_timezone)
        end = datetime(end_year, end_month, 1, tzinfo=reporting_timezone)
        return cls(
            start=start.astimezone(dt_timezone.utc),
            end=end.astimezone(dt_timezone.utc),
            timezone=timezone,
            kind="quarter",
            label=f"{year} Q{quarter}",
        )
