from datetime import datetime
from datetime import timezone as dt_timezone

import pytest

from totem.reporting.periods import ReportPeriod


def test_calendar_quarter_uses_local_midnight_boundaries():
    period = ReportPeriod.calendar_quarter(2026, 1, "America/Los_Angeles")

    assert period.start == datetime(2026, 1, 1, 8, tzinfo=dt_timezone.utc)
    assert period.end == datetime(2026, 4, 1, 7, tzinfo=dt_timezone.utc)
    assert period.label == "2026 Q1"
    assert period.kind == "quarter"


def test_calendar_year_has_an_exclusive_end():
    period = ReportPeriod.calendar_year(2026, "UTC")

    assert period.start == datetime(2026, 1, 1, tzinfo=dt_timezone.utc)
    assert period.end == datetime(2027, 1, 1, tzinfo=dt_timezone.utc)
    assert period.label == "2026"
    assert period.kind == "year"


def test_calendar_quarter_rejects_invalid_quarter():
    with pytest.raises(ValueError, match="between 1 and 4"):
        ReportPeriod.calendar_quarter(2026, 5, "UTC")
