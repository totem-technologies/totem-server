from datetime import datetime, timedelta

from django.db.models import CharField, DurationField, ExpressionWrapper, F, Prefetch, QuerySet
from django.db.models.functions import Coalesce

from totem.reporting.periods import ReportPeriod
from totem.reporting.types import ReportFilters, SessionFact
from totem.spaces.models import Session, SessionFeedback, SessionFeedbackOptions
from totem.users.models import User


def load_session_facts(*, period: ReportPeriod, filters: ReportFilters) -> tuple[SessionFact, ...]:
    feedback = SessionFeedback.objects.only("session_id", "user_id", "feedback")
    participant_ids = User.objects.only("id")
    sessions = (
        Session.objects.filter(start__gte=period.start, start__lt=period.end)
        .select_related("space", "space__author", "room")
        .only(
            "slug",
            "start",
            "duration_minutes",
            "seats",
            "cancelled",
            "space__slug",
            "space__author_id",
            "space__author__slug",
            "room__keeper",
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
        sessions = sessions.annotate(
            reporting_keeper_slug=Coalesce("room__keeper", "space__author__slug", output_field=CharField())
        ).filter(reporting_keeper_slug__in=filters.keeper_slugs)
    if filters.category_slugs:
        sessions = sessions.filter(space__categories__slug__in=filters.category_slugs).distinct()

    sessions = tuple(sessions)
    rooms = {session.pk: getattr(session, "room", None) for session in sessions}
    room_keeper_slugs = {room.keeper for room in rooms.values() if room is not None}
    keeper_ids = dict(User.objects.filter(slug__in=room_keeper_slugs).values_list("slug", "id"))

    facts = []
    for session in sessions:
        room = rooms[session.pk]
        keeper_slug = room.keeper if room is not None else session.space.author.slug
        keeper_id = keeper_ids.get(keeper_slug, session.space.author_id if room is None else None)
        rsvp_ids = frozenset(user.id for user in session.attendees.all() if keeper_id is None or user.id != keeper_id)
        joined_ids = frozenset(user.id for user in session.joined.all())
        beneficiary_ids = joined_ids - ({keeper_id} if keeper_id is not None else set())
        valid_feedback = tuple(item for item in session.feedback.all() if item.user_id in beneficiary_ids)
        facts.append(
            SessionFact(
                session_slug=session.slug,
                space_slug=session.space.slug,
                keeper_slug=keeper_slug,
                scheduled_start=session.start,
                scheduled_end=session.start + timedelta(minutes=session.duration_minutes),
                seats=session.seats,
                cancelled=session.cancelled,
                keeper_joined=keeper_id is not None and keeper_id in joined_ids,
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
    ).exclude(user__slug=Coalesce("session__room__keeper", "session__space__author__slug", output_field=CharField()))
    return frozenset(joined.values_list("user_id", flat=True))


def beneficiary_feedback(*, as_of: datetime) -> QuerySet[SessionFeedback]:
    """Feedback that counts toward satisfaction metrics.

    Applies the same rules as the feedback metrics in session_metrics: the respondent joined the
    session and is not its keeper, and the session was not cancelled and has reached its scheduled end.
    """

    duration = ExpressionWrapper(F("session__duration_minutes") * timedelta(minutes=1), output_field=DurationField())
    return (
        SessionFeedback.objects.alias(scheduled_end=F("session__start") + duration)
        .filter(session__cancelled=False, session__joined=F("user"), scheduled_end__lte=as_of)
        .exclude(user__slug=Coalesce("session__room__keeper", "session__space__author__slug", output_field=CharField()))
    )
