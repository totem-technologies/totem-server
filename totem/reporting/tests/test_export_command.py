import csv
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from totem.spaces.tests.factories import SessionFactory, SpaceCategoryFactory, SpaceFactory
from totem.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


EXPECTED_COLUMNS = [
    "metric_name",
    "value",
    "unit",
    "numerator",
    "denominator",
    "period_start",
    "period_end",
    "reporting_timezone",
    "period_kind",
    "period_label",
    "cohort",
    "generated_at",
    "definition_version",
]


def _read_stdout(*args: str) -> tuple[list[str], dict[str, dict[str, str]]]:
    stdout = StringIO()
    call_command("export_analytics", *args, stdout=stdout)
    reader = csv.DictReader(StringIO(stdout.getvalue()))
    return reader.fieldnames or [], {row["metric_name"]: row for row in reader}


def test_exports_a_year_as_aggregate_only_csv():
    keeper = UserFactory(is_staff=True, email="keeper@example.com", name="Private Keeper")
    participant = UserFactory(email="participant@example.com", name="Private Participant")
    session = SessionFactory(
        space=SpaceFactory(author=keeper),
        start=datetime(2026, 1, 15, 12, tzinfo=dt_timezone.utc),
        duration_minutes=60,
    )
    session.joined.add(keeper, participant)

    columns, metrics = _read_stdout("--year", "2026", "--timezone", "UTC")

    assert columns == EXPECTED_COLUMNS
    assert metrics["elapsed_session_slots"]["value"] == "1"
    assert metrics["sessions_with_beneficiary_attendance"]["value"] == "1"
    assert metrics["beneficiary_reach_rate"]["value"] == "1"
    assert metrics["beneficiary_reach_rate"]["numerator"] == "1"
    assert metrics["beneficiary_reach_rate"]["denominator"] == "1"
    assert metrics["elapsed_session_slots"]["period_start"] == "2026-01-01T00:00:00+00:00"
    assert metrics["elapsed_session_slots"]["period_end"] == "2027-01-01T00:00:00+00:00"
    assert metrics["elapsed_session_slots"]["period_label"] == "2026"

    exported = "\n".join(",".join(row.values()) for row in metrics.values())
    assert "keeper@example.com" not in exported
    assert "participant@example.com" not in exported
    assert "Private Keeper" not in exported
    assert "Private Participant" not in exported


def test_exports_a_slug_filtered_quarter():
    as_of = datetime.now(tz=dt_timezone.utc)
    category = SpaceCategoryFactory(slug="grief-support")
    included_space = SpaceFactory(slug="included-space", categories=[category])
    excluded_space = SpaceFactory(slug="excluded-space")
    included = SessionFactory(space=included_space, start=as_of - timedelta(days=1))
    excluded = SessionFactory(space=excluded_space, start=as_of - timedelta(days=1))
    participant = UserFactory()
    included.joined.add(participant)
    excluded.joined.add(participant)

    quarter = (as_of.month - 1) // 3 + 1
    _, metrics = _read_stdout(
        "--quarter",
        f"{as_of.year}-Q{quarter}",
        "--timezone",
        "UTC",
        "--category",
        category.slug,
        "--space",
        included_space.slug,
    )

    assert metrics["elapsed_session_slots"]["value"] == "1"
    assert metrics["service_units"]["value"] == "1"
    assert metrics["elapsed_session_slots"]["cohort"] == ("spaces=included-space;categories=grief-support")


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (("--year", "2026", "--quarter", "2026-Q1", "--timezone", "UTC"), "not allowed"),
        (("--quarter", "2026-1", "--timezone", "UTC"), "YYYY-QN"),
        (("--year", "2026", "--timezone", "Not/A_Timezone"), "Unknown timezone"),
    ],
)
def test_rejects_ambiguous_or_invalid_periods(arguments: tuple[str, ...], message: str):
    with pytest.raises(CommandError, match=message):
        call_command("export_analytics", *arguments)
