from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from datetime import timezone as dttz
from typing import Any

from django.db.models import Count, Q, QuerySet, Sum
from django.utils import timezone

from totem.spaces.models import Session

UTC = dttz.utc


@dataclass(frozen=True)
class DateRange:
    start: datetime
    end: datetime  # exclusive

    def label(self) -> str:
        inclusive_end = (self.end - timedelta(microseconds=1)).date()
        return f"{self.start.date()} to {inclusive_end}"


@dataclass(frozen=True)
class SessionStats:
    date_range: DateRange
    total_sessions: int
    sessions_with_signups: int
    sessions_no_signups: int
    total_signups: int
    unique_signups: int
    sessions_with_participants: int
    sessions_no_participants: int
    total_participants: int
    unique_participants: int
    avg_signups_per_session: float | None
    avg_participants_per_session: float | None
    top_sessions: list[dict[str, Any]]

    def asdict(self) -> dict[str, Any]:
        data = asdict(self)
        data["date_range"] = {"start": self.date_range.start.isoformat(), "end": self.date_range.end.isoformat()}
        return data


def get_year_range(year: int) -> DateRange:
    start = datetime(year, 1, 1, tzinfo=UTC)
    end = datetime(year + 1, 1, 1, tzinfo=UTC)
    return DateRange(start=start, end=end)


def get_month_range(year: int, month: int) -> DateRange:
    if month < 1 or month > 12:
        raise ValueError("month must be in 1..12")
    start = datetime(year, month, 1, tzinfo=UTC)
    if month == 12:
        end = datetime(year + 1, 1, 1, tzinfo=UTC)
    else:
        end = datetime(year, month + 1, 1, tzinfo=UTC)
    return DateRange(start=start, end=end)


def _parse_date(value: str) -> date:
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("Invalid date format. Use 'YYYY-MM-DD'") from exc


def get_date_range(period: str = "last_quarter") -> DateRange:
    now = timezone.now().astimezone(UTC)

    if period == "all_time":
        return DateRange(start=datetime(1970, 1, 1, tzinfo=UTC), end=now)

    if period == "last_quarter":
        current_quarter = (now.month - 1) // 3 + 1  # 1-4
        previous_quarter = current_quarter - 1 if current_quarter > 1 else 4
        year = now.year if current_quarter > 1 else now.year - 1
        start_month = 3 * (previous_quarter - 1) + 1  # Q1=1, Q2=4, Q3=7, Q4=10
        start = datetime(year, start_month, 1, tzinfo=UTC)
        if start_month == 10:
            end = datetime(year + 1, 1, 1, tzinfo=UTC)
        else:
            end = datetime(year, start_month + 3, 1, tzinfo=UTC)
        return DateRange(start=start, end=end)

    if period == "last_month":
        first_of_this_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        last_of_prev_month = first_of_this_month - timedelta(days=1)
        start = last_of_prev_month.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = first_of_this_month
        return DateRange(start=start, end=end)

    if period == "last_week":
        return DateRange(start=now - timedelta(days=7), end=now)

    # Custom: "YYYY-MM-DD,YYYY-MM-DD" (end date inclusive)
    try:
        start_raw, end_raw = period.split(",", 1)
        start_date = _parse_date(start_raw)
        end_date = _parse_date(end_raw)
    except ValueError as exc:
        raise ValueError("Invalid date range format. Use 'YYYY-MM-DD,YYYY-MM-DD'") from exc

    start = datetime.combine(start_date, datetime.min.time(), tzinfo=UTC)
    end = datetime.combine(end_date + timedelta(days=1), datetime.min.time(), tzinfo=UTC)
    return DateRange(start=start, end=end)


def session_queryset(
    *,
    date_range: DateRange,
    space_id: int | None = None,
    event_id: int | None = None,
    author_slug: str | None = None,
) -> QuerySet[Session]:
    filters = Q(start__gte=date_range.start) & Q(start__lt=date_range.end) & Q(cancelled=False)
    if space_id is not None:
        filters &= Q(circle_id=space_id)
    if event_id is not None:
        filters &= Q(id=event_id)
    if author_slug is not None:
        filters &= Q(space__author__slug=author_slug)
    return Session.objects.filter(filters)


def _session_fk_field_name(through_model) -> str:
    # Avoid hard-coding the through-table FK name for sessions.
    for field in through_model._meta.fields:
        if getattr(field.remote_field, "model", None) is Session:
            return field.name
    raise RuntimeError("Session FK not found in through model.")


def compute_session_stats(
    *,
    date_range: DateRange,
    space_id: int | None = None,
    event_id: int | None = None,
    author_slug: str | None = None,
    top_sessions: int = 5,
) -> SessionStats:
    sessions = session_queryset(
        date_range=date_range,
        space_id=space_id,
        event_id=event_id,
        author_slug=author_slug,
    )

    total_sessions = sessions.count()

    # Signups (users who registered for a session)
    signup_through = Session.attendees.through
    signup_session_field = _session_fk_field_name(signup_through)
    signup_links = signup_through.objects.filter(**{f"{signup_session_field}__in": sessions.values("id")})
    total_signups = signup_links.count()
    unique_signups = signup_links.values("user_id").distinct().count()

    signups_per_session = signup_links.values(signup_session_field).annotate(signup_count=Count("user_id"))
    signups_per_session_with_people = signups_per_session.filter(signup_count__gt=1)
    sessions_with_signups = signups_per_session_with_people.count()
    sessions_no_signups = total_sessions - sessions_with_signups
    total_signups_in_active_sessions = (
        signups_per_session_with_people.aggregate(total=Sum("signup_count"))["total"] or 0
    )
    avg_signups_per_session = (
        (total_signups_in_active_sessions / sessions_with_signups) if sessions_with_signups > 0 else None
    )

    # Participants (users who actually attended)
    participant_through = Session.joined.through
    participant_session_field = _session_fk_field_name(participant_through)
    participant_links = participant_through.objects.filter(
        **{f"{participant_session_field}__in": sessions.values("id")}
    )
    total_participants = participant_links.count()
    unique_participants = participant_links.values("user_id").distinct().count()

    participants_per_session = participant_links.values(participant_session_field).annotate(
        participant_count=Count("user_id")
    )
    participants_per_session_with_people = participants_per_session.filter(participant_count__gt=1)
    sessions_with_participants = participants_per_session_with_people.count()
    sessions_no_participants = total_sessions - sessions_with_participants
    total_participants_in_active_sessions = (
        participants_per_session_with_people.aggregate(total=Sum("participant_count"))["total"] or 0
    )
    avg_participants_per_session = (
        (total_participants_in_active_sessions / sessions_with_participants) if sessions_with_participants > 0 else None
    )

    top_sessions_data: list[dict[str, Any]] = []
    if top_sessions > 0:
        for session in (
            sessions.select_related("space")
            .annotate(
                signup_count=Count("attendees", distinct=True),
                participant_count=Count("joined", distinct=True),
            )
            .filter(signup_count__gt=0)
            .order_by("-signup_count", "-participant_count", "start")[:top_sessions]
        ):
            top_sessions_data.append(
                {
                    "space_title": session.space.title,
                    "session_slug": session.slug,
                    "start": session.start.isoformat(),
                    "signups": session.signup_count,
                    "participants": session.participant_count,
                }
            )

    return SessionStats(
        date_range=date_range,
        total_sessions=total_sessions,
        sessions_with_signups=sessions_with_signups,
        sessions_no_signups=sessions_no_signups,
        total_signups=total_signups,
        unique_signups=unique_signups,
        sessions_with_participants=sessions_with_participants,
        sessions_no_participants=sessions_no_participants,
        total_participants=total_participants,
        unique_participants=unique_participants,
        avg_signups_per_session=avg_signups_per_session,
        avg_participants_per_session=avg_participants_per_session,
        top_sessions=top_sessions_data,
    )
