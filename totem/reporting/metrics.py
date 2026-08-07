from collections import Counter
from datetime import datetime
from decimal import Decimal

from totem.reporting.facts import load_session_facts, previous_beneficiary_ids
from totem.reporting.periods import ReportPeriod
from totem.reporting.types import MetricResult, ReportFilters

DEFINITION_VERSION = "1.0"


def _ratio(numerator: int, denominator: int) -> Decimal | None:
    if denominator == 0:
        return None
    return Decimal(numerator) / Decimal(denominator)


def session_metrics(
    *,
    period: ReportPeriod,
    as_of: datetime,
    filters: ReportFilters | None = None,
) -> tuple[MetricResult, ...]:
    """Compute aggregate session metrics without relying on Session.ended_at."""

    if as_of.tzinfo is None:
        raise ValueError("Metric generation time must be timezone-aware")

    filters = filters or ReportFilters()
    facts = load_session_facts(period=period, filters=filters)
    elapsed = tuple(fact for fact in facts if not fact.cancelled and fact.scheduled_end <= as_of)
    upcoming = tuple(fact for fact in facts if not fact.cancelled and fact.scheduled_end > as_of)
    attendance_sessions = tuple(fact for fact in elapsed if fact.beneficiary_attendance_ids)
    no_attendance_sessions = tuple(fact for fact in elapsed if not fact.beneficiary_attendance_ids)

    attendance_counts = Counter(
        participant_id for fact in elapsed for participant_id in fact.beneficiary_attendance_ids
    )
    current_participant_ids = frozenset(attendance_counts)
    prior_participant_ids = previous_beneficiary_ids(before=period.start)
    returning_ids = current_participant_ids & prior_participant_ids
    new_ids = current_participant_ids - prior_participant_ids

    service_units = sum(attendance_counts.values())
    unique_participants = len(current_participant_ids)
    repeat_participants = sum(count >= 2 for count in attendance_counts.values())
    final_rsvps = sum(len(fact.beneficiary_rsvp_ids) for fact in elapsed)
    no_shows = sum(len(fact.beneficiary_rsvp_ids - fact.beneficiary_attendance_ids) for fact in elapsed)
    walk_ins = sum(len(fact.beneficiary_attendance_ids - fact.beneficiary_rsvp_ids) for fact in elapsed)
    recognized_rsvp_cohort = sum(len(fact.beneficiary_rsvp_ids | fact.beneficiary_attendance_ids) for fact in elapsed)
    feedback_responses = sum(len(fact.feedback_respondent_ids) for fact in elapsed)
    positive_feedback_responses = sum(len(fact.positive_feedback_respondent_ids) for fact in elapsed)

    def result(
        metric_name: str,
        value: int | Decimal | None,
        unit: str,
        *,
        numerator: int | None = None,
        denominator: int | None = None,
    ) -> MetricResult:
        return MetricResult(
            metric_name=metric_name,
            value=value,
            unit=unit,
            numerator=numerator,
            denominator=denominator,
            period_start=period.start,
            period_end=period.end,
            reporting_timezone=period.timezone,
            period_kind=period.kind,
            period_label=period.label,
            cohort=filters.description(),
            generated_at=as_of,
            definition_version=DEFINITION_VERSION,
        )

    return (
        result("elapsed_session_slots", len(elapsed), "sessions"),
        result("sessions_with_beneficiary_attendance", len(attendance_sessions), "sessions"),
        result("sessions_without_beneficiary_attendance", len(no_attendance_sessions), "sessions"),
        result(
            "keeper_only_session_slots",
            sum(fact.keeper_joined for fact in no_attendance_sessions),
            "sessions",
        ),
        result(
            "empty_session_slots",
            sum(not fact.keeper_joined for fact in no_attendance_sessions),
            "sessions",
        ),
        result("cancelled_sessions", sum(fact.cancelled for fact in facts), "sessions"),
        result("upcoming_session_slots", len(upcoming), "sessions"),
        result(
            "beneficiary_reach_rate",
            _ratio(len(attendance_sessions), len(elapsed)),
            "ratio",
            numerator=len(attendance_sessions),
            denominator=len(elapsed),
        ),
        result("service_units", service_units, "attendances"),
        result("unique_participants", unique_participants, "people"),
        result("new_participants", len(new_ids), "people"),
        result("returning_participants", len(returning_ids), "people"),
        result("repeat_participants", repeat_participants, "people"),
        result(
            "repeat_rate",
            _ratio(repeat_participants, unique_participants),
            "ratio",
            numerator=repeat_participants,
            denominator=unique_participants,
        ),
        result(
            "average_beneficiaries_per_attendance_session",
            _ratio(service_units, len(attendance_sessions)),
            "people_per_session",
            numerator=service_units,
            denominator=len(attendance_sessions),
        ),
        result(
            "average_sessions_per_participant",
            _ratio(service_units, unique_participants),
            "sessions_per_person",
            numerator=service_units,
            denominator=unique_participants,
        ),
        result("final_beneficiary_rsvps", final_rsvps, "rsvps"),
        result("beneficiary_no_shows", no_shows, "rsvps"),
        result("attended_without_final_rsvp", walk_ins, "attendances"),
        result("recognized_rsvp_cohort", recognized_rsvp_cohort, "people"),
        result(
            "attendance_rate",
            _ratio(service_units, recognized_rsvp_cohort),
            "ratio",
            numerator=service_units,
            denominator=recognized_rsvp_cohort,
        ),
        result("feedback_responses", feedback_responses, "responses"),
        result("positive_feedback_responses", positive_feedback_responses, "responses"),
        result(
            "satisfaction_rate",
            _ratio(positive_feedback_responses, feedback_responses),
            "ratio",
            numerator=positive_feedback_responses,
            denominator=feedback_responses,
        ),
        result(
            "feedback_response_rate",
            _ratio(feedback_responses, service_units),
            "ratio",
            numerator=feedback_responses,
            denominator=service_units,
        ),
    )
