from datetime import timedelta

from django.db.models import F, Prefetch

from totem.reporting.periods import ReportPeriod
from totem.reporting.types import ReportFilters, SessionFact
from totem.spaces.models import Session, SessionFeedback, SessionFeedbackOptions
from totem.users.models import User


def load_session_facts(*, period: ReportPeriod, filters: ReportFilters) -> tuple[SessionFact, ...]:
    feedback = SessionFeedback.objects.only("session_id", "user_id", "feedback")
    participant_ids = User.objects.only("id")
    sessions = (
        Session.objects.filter(start__gte=period.start, start__lt=period.end)
        .select_related("space", "space__author")
        .only(
            "slug",
            "start",
            "duration_minutes",
            "seats",
            "cancelled",
            "space__slug",
            "space__author_id",
            "space__author__slug",
        )
        .prefetch_related(
            Prefetch("attendees", queryset=participant_ids),
            Prefetch("joined", queryset=participant_ids),
            Prefetch("feedback", queryset=feedback),
        )
    )

    if filters.session_slugs:
        sessions = sessions.filter(slug__in=filters.session_slugs)
    if filters.space_slugs:
        sessions = sessions.filter(space__slug__in=filters.space_slugs)
    if filters.keeper_slugs:
        sessions = sessions.filter(space__author__slug__in=filters.keeper_slugs)
    if filters.category_slugs:
        sessions = sessions.filter(space__categories__slug__in=filters.category_slugs).distinct()

    facts = []
    for session in sessions:
        keeper_id = session.space.author_id
        rsvp_ids = frozenset(user.id for user in session.attendees.all() if user.id != keeper_id)
        joined_ids = frozenset(user.id for user in session.joined.all())
        beneficiary_ids = joined_ids - {keeper_id}
        valid_feedback = tuple(item for item in session.feedback.all() if item.user_id in beneficiary_ids)
        facts.append(
            SessionFact(
                session_slug=session.slug,
                space_slug=session.space.slug,
                keeper_slug=session.space.author.slug,
                scheduled_start=session.start,
                scheduled_end=session.start + timedelta(minutes=session.duration_minutes),
                seats=session.seats,
                cancelled=session.cancelled,
                keeper_joined=keeper_id in joined_ids,
                beneficiary_rsvp_ids=rsvp_ids,
                beneficiary_attendance_ids=beneficiary_ids,
                feedback_respondent_ids=frozenset(item.user_id for item in valid_feedback),
                positive_feedback_respondent_ids=frozenset(
                    item.user_id for item in valid_feedback if item.feedback == SessionFeedbackOptions.UP
                ),
            )
        )
    return tuple(facts)


def previous_beneficiary_ids(*, before) -> frozenset[int]:
    """Participants recorded as joining any non-cancelled session before a period."""

    joined = Session.joined.through.objects.filter(
        session__cancelled=False,
        session__start__lt=before,
    ).exclude(user_id=F("session__space__author_id"))
    return frozenset(joined.values_list("user_id", flat=True))
