from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from datetime import timezone as dttz
from typing import Any

from django.db.models import Count, Q, QuerySet, Sum
from django.utils import timezone

from totem.circles.models import CircleEvent

UTC = dttz.utc


@dataclass(frozen=True)
class DateRange:
    start: datetime
    end: datetime  # exclusive

    def label(self) -> str:
        inclusive_end = (self.end - timedelta(microseconds=1)).date()
        return f"{self.start.date()} to {inclusive_end}"


@dataclass(frozen=True)
class CircleEventStats:
    date_range: DateRange
    total_events: int
    events_with_attendees: int
    events_no_attendees: int
    total_attendees: int
    unique_attendees: int
    events_with_joins: int
    events_no_joins: int
    total_joins: int
    unique_joins: int
    avg_attendees_per_event: float | None
    avg_joins_per_event: float | None
    top_events: list[dict[str, Any]]

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


def circle_event_queryset(
    *,
    date_range: DateRange,
    circle_id: int | None = None,
    event_id: int | None = None,
    author_slug: str | None = None,
) -> QuerySet[CircleEvent]:
    filters = Q(start__gte=date_range.start) & Q(start__lt=date_range.end)
    if circle_id is not None:
        filters &= Q(circle_id=circle_id)
    if event_id is not None:
        filters &= Q(id=event_id)
    if author_slug is not None:
        filters &= Q(circle__author__slug=author_slug)
    return CircleEvent.objects.filter(filters)


def compute_circle_event_stats(
    *,
    date_range: DateRange,
    circle_id: int | None = None,
    event_id: int | None = None,
    author_slug: str | None = None,
    top_events: int = 5,
) -> CircleEventStats:
    events = circle_event_queryset(
        date_range=date_range,
        circle_id=circle_id,
        event_id=event_id,
        author_slug=author_slug,
    )

    total_events = events.count()

    # Attendees
    attendee_links = CircleEvent.attendees.through.objects.filter(circleevent_id__in=events.values("id"))
    total_attendees = attendee_links.count()
    unique_attendees = attendee_links.values("user_id").distinct().count()

    attendees_per_event = attendee_links.values("circleevent_id").annotate(attendee_count=Count("user_id"))
    attendees_per_event_with_people = attendees_per_event.filter(attendee_count__gt=1)
    events_with_attendees = attendees_per_event_with_people.count()
    events_no_attendees = total_events - events_with_attendees
    total_attendees_in_attended_events = (
        attendees_per_event_with_people.aggregate(total=Sum("attendee_count"))["total"] or 0
    )
    avg_attendees_per_event = (
        (total_attendees_in_attended_events / events_with_attendees) if events_with_attendees > 0 else None
    )

    # Joins
    joined_links = CircleEvent.joined.through.objects.filter(circleevent_id__in=events.values("id"))
    total_joins = joined_links.count()
    unique_joins = joined_links.values("user_id").distinct().count()

    joins_per_event = joined_links.values("circleevent_id").annotate(joined_count=Count("user_id"))
    joins_per_event_with_people = joins_per_event.filter(joined_count__gt=1)
    events_with_joins = joins_per_event_with_people.count()
    events_no_joins = total_events - events_with_joins
    total_joins_in_joined_events = joins_per_event_with_people.aggregate(total=Sum("joined_count"))["total"] or 0
    avg_joins_per_event = (total_joins_in_joined_events / events_with_joins) if events_with_joins > 0 else None

    top_events_data: list[dict[str, Any]] = []
    if top_events > 0:
        for event in (
            events.select_related("circle")
            .annotate(
                attendee_count=Count("attendees", distinct=True),
                joined_count=Count("joined", distinct=True),
            )
            .filter(attendee_count__gt=0)
            .order_by("-attendee_count", "-joined_count", "start")[:top_events]
        ):
            top_events_data.append(
                {
                    "circle_title": event.circle.title,
                    "event_slug": event.slug,
                    "start": event.start.isoformat(),
                    "attendees": event.attendee_count,
                    "joined": event.joined_count,
                }
            )

    return CircleEventStats(
        date_range=date_range,
        total_events=total_events,
        events_with_attendees=events_with_attendees,
        events_no_attendees=events_no_attendees,
        total_attendees=total_attendees,
        unique_attendees=unique_attendees,
        events_with_joins=events_with_joins,
        events_no_joins=events_no_joins,
        total_joins=total_joins,
        unique_joins=unique_joins,
        avg_attendees_per_event=avg_attendees_per_event,
        avg_joins_per_event=avg_joins_per_event,
        top_events=top_events_data,
    )
