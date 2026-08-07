from dataclasses import fields
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from decimal import Decimal

import pytest

from totem.reporting.metrics import session_metrics
from totem.reporting.periods import ReportPeriod
from totem.reporting.types import MetricResult, ReportFilters
from totem.spaces.models import SessionFeedback, SessionFeedbackOptions
from totem.spaces.tests.factories import SessionFactory, SpaceCategoryFactory, SpaceFactory
from totem.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def _metrics_by_name(*, period: ReportPeriod, as_of: datetime, filters: ReportFilters | None = None):
    return {
        result.metric_name: result
        for result in session_metrics(period=period, as_of=as_of, filters=filters or ReportFilters())
    }


def test_collapses_session_delivery_without_using_ended_at():
    period = ReportPeriod.calendar_quarter(2026, 3, "UTC")
    as_of = datetime(2026, 8, 3, 12, tzinfo=dt_timezone.utc)
    keeper = UserFactory(is_staff=True)
    participant = UserFactory()
    space = SpaceFactory(author=keeper)

    keeper_only = SessionFactory(
        space=space,
        start=as_of - timedelta(days=2),
        duration_minutes=60,
        ended_at=None,
    )
    keeper_only.attendees.add(keeper)
    keeper_only.joined.add(keeper)

    beneficiary_only = SessionFactory(
        space=space,
        start=as_of - timedelta(days=1),
        duration_minutes=60,
        ended_at=as_of + timedelta(days=30),
    )
    beneficiary_only.attendees.add(participant)
    beneficiary_only.joined.add(participant)

    cancelled = SessionFactory(space=space, start=as_of - timedelta(days=3), cancelled=True)
    cancelled.joined.add(participant)

    in_progress = SessionFactory(
        space=space,
        start=as_of - timedelta(minutes=30),
        duration_minutes=60,
        ended_at=as_of - timedelta(minutes=20),
    )
    in_progress.joined.add(participant)
    SessionFactory(space=space, start=as_of + timedelta(days=1))

    metrics = _metrics_by_name(period=period, as_of=as_of)

    assert metrics["elapsed_session_slots"].value == 2
    assert metrics["sessions_with_beneficiary_attendance"].value == 1
    assert metrics["sessions_without_beneficiary_attendance"].value == 1
    assert metrics["keeper_only_session_slots"].value == 1
    assert metrics["empty_session_slots"].value == 0
    assert metrics["cancelled_sessions"].value == 1
    assert metrics["upcoming_session_slots"].value == 2
    assert metrics["beneficiary_reach_rate"].value == Decimal("0.5")
    assert metrics["service_units"].value == 1

    result_fields = {field.name for field in fields(MetricResult)}
    assert result_fields.isdisjoint({"email", "name", "user_slug", "participant_ids"})


def test_computes_engagement_rsvp_and_feedback_metrics():
    period = ReportPeriod.calendar_quarter(2026, 3, "UTC")
    as_of = datetime(2026, 8, 3, 12, tzinfo=dt_timezone.utc)
    keeper = UserFactory(is_staff=True)
    returning = UserFactory()
    newcomer = UserFactory()
    walk_in = UserFactory()
    no_show = UserFactory()
    space = SpaceFactory(author=keeper)

    previous = SessionFactory(space=space, start=period.start - timedelta(days=7))
    previous.attendees.add(keeper, returning)
    previous.joined.add(keeper, returning)

    first = SessionFactory(space=space, start=as_of - timedelta(days=2))
    first.attendees.add(keeper, returning, newcomer, no_show)
    first.joined.add(keeper, returning, newcomer)

    second = SessionFactory(space=space, start=as_of - timedelta(days=1))
    second.attendees.add(keeper, returning)
    second.joined.add(returning, walk_in)

    SessionFeedback.objects.create(session=first, user=returning, feedback=SessionFeedbackOptions.UP)
    SessionFeedback.objects.create(session=first, user=newcomer, feedback=SessionFeedbackOptions.DOWN)
    SessionFeedback.objects.create(session=first, user=keeper, feedback=SessionFeedbackOptions.UP)
    SessionFeedback.objects.create(session=first, user=no_show, feedback=SessionFeedbackOptions.UP)

    metrics = _metrics_by_name(period=period, as_of=as_of)

    assert metrics["service_units"].value == 4
    assert metrics["unique_participants"].value == 3
    assert metrics["new_participants"].value == 2
    assert metrics["returning_participants"].value == 1
    assert metrics["repeat_participants"].value == 1
    assert metrics["repeat_rate"].value == Decimal(1) / Decimal(3)
    assert metrics["average_beneficiaries_per_attendance_session"].value == Decimal(2)
    assert metrics["average_sessions_per_participant"].value == Decimal(4) / Decimal(3)

    assert metrics["final_beneficiary_rsvps"].value == 4
    assert metrics["beneficiary_no_shows"].value == 1
    assert metrics["attended_without_final_rsvp"].value == 1
    assert metrics["recognized_rsvp_cohort"].value == 5
    assert metrics["attendance_rate"].value == Decimal("0.8")

    assert metrics["feedback_responses"].value == 2
    assert metrics["positive_feedback_responses"].value == 1
    assert metrics["satisfaction_rate"].value == Decimal("0.5")
    assert metrics["feedback_response_rate"].value == Decimal("0.5")


def test_filters_by_human_readable_slugs():
    period = ReportPeriod.calendar_quarter(2026, 3, "UTC")
    as_of = datetime(2026, 8, 3, 12, tzinfo=dt_timezone.utc)
    first_keeper = UserFactory(is_staff=True)
    second_keeper = UserFactory(is_staff=True)
    participant = UserFactory()
    category = SpaceCategoryFactory(slug="grief-support")
    first_space = SpaceFactory(author=first_keeper, slug="first-space", categories=[category])
    second_space = SpaceFactory(author=second_keeper, slug="second-space")
    first_session = SessionFactory(space=first_space, slug="first-session", start=as_of - timedelta(days=2))
    second_session = SessionFactory(space=second_space, slug="second-session", start=as_of - timedelta(days=1))
    first_session.joined.add(participant)
    second_session.joined.add(participant)

    filter_cases = (
        ReportFilters(session_slugs=(first_session.slug,)),
        ReportFilters(space_slugs=(first_space.slug,)),
        ReportFilters(keeper_slugs=(first_keeper.slug,)),
        ReportFilters(category_slugs=(category.slug,)),
    )

    for filters in filter_cases:
        metrics = _metrics_by_name(period=period, as_of=as_of, filters=filters)
        assert metrics["elapsed_session_slots"].value == 1
        assert metrics["service_units"].value == 1


def test_rates_are_unknown_when_their_cohort_is_empty():
    period = ReportPeriod.calendar_quarter(2026, 3, "UTC")
    metrics = _metrics_by_name(
        period=period,
        as_of=datetime(2026, 8, 3, 12, tzinfo=dt_timezone.utc),
    )

    rate_names = (
        "beneficiary_reach_rate",
        "repeat_rate",
        "average_beneficiaries_per_attendance_session",
        "average_sessions_per_participant",
        "attendance_rate",
        "satisfaction_rate",
        "feedback_response_rate",
    )
    for metric_name in rate_names:
        assert metrics[metric_name].value is None
        assert metrics[metric_name].denominator == 0


def test_metric_generation_time_must_be_timezone_aware():
    period = ReportPeriod.calendar_quarter(2026, 3, "UTC")

    with pytest.raises(ValueError, match="timezone-aware"):
        session_metrics(period=period, as_of=datetime(2026, 8, 3))
