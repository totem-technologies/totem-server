import datetime

from django.db.models import Count, F, OuterRef, Q, Subquery
from django.urls import reverse
from django.utils import timezone

from totem.spaces.schemas import NextSessionSchema, SessionDetailSchema, SessionSpaceSchema, SpaceDetailSchema
from totem.users.models import User

from .models import Session, Space, SpaceCategory


def other_sessions_in_space(user: User | None, session: Session, limit: int = 10):
    sessions = Session.objects.filter(space=session.space, start__gte=timezone.now(), cancelled=False).distinct()
    if user and user.is_authenticated:
        # show users events they are already attending
        sessions = sessions.filter(Q(open=True, listed=True) | Q(attendees=user))
    else:
        sessions = sessions.filter(open=True, listed=True)
    sessions = sessions.exclude(slug=session.slug)
    sessions = sessions.order_by("start")
    if not user or not user.is_staff:
        sessions = sessions.filter(space__published=True)
    return sessions[:limit]


def sessions_by_month(user: User | None, space_slug: str, month: int, year: int):
    startDate = datetime.datetime(year, month, 1, tzinfo=datetime.timezone.utc)
    endDate = startDate + datetime.timedelta(days=32)
    sessions = Session.objects.filter(start__gte=startDate, start__lte=endDate, cancelled=False, space__slug=space_slug)
    if user and user.is_authenticated:
        # show users events they are already attending
        sessions = sessions.filter(Q(open=True, listed=True) | Q(attendees=user))
    else:
        sessions = sessions.filter(open=True, listed=True)
    sessions = sessions.order_by("start")
    if not user or not user.is_staff:
        sessions = sessions.filter(space__published=True)
    return sessions


def all_upcoming_recommended_sessions(user: User | None, category: str | None = None, author: str | None = None):
    sessions = Session.objects.filter(start__gte=timezone.now(), cancelled=False, listed=True)
    sessions = sessions.order_by("start")
    if not user or not user.is_staff:
        sessions = sessions.filter(space__published=True)
    # are there any seats?
    sessions = sessions.annotate(attendee_count=Count("attendees")).filter(attendee_count__lt=F("seats"))
    # filter category
    if category:
        sessions = sessions.filter(space__categories__slug=category) | sessions.filter(space__categories__name=category)
    # filter author
    if author:
        sessions = sessions.filter(space__author__slug=author)
    sessions = sessions.prefetch_related("space__author")
    return sessions


def upcoming_recommended_sessions(user: User | None, categories: list[str] | None = None, author: str | None = None):
    sessions = (
        Session.objects.filter(start__gte=timezone.now(), cancelled=False, listed=True)
        .select_related("space")
        .prefetch_related("space__author", "space__categories", "space__subscribed")
        .annotate(
            attendee_count=Count("attendees", distinct=True),
            subscriber_count=Count("space__subscribed", distinct=True),
        )
        .order_by("start")
    )
    if not user or not user.is_staff:
        sessions = sessions.filter(space__published=True)
    # are there any seats?
    sessions = sessions.filter(attendee_count__lt=F("seats"))
    # filter category
    if categories:
        sessions = sessions.filter(
            Q(space__categories__slug__in=categories) | Q(space__categories__name__in=categories)
        )
    # filter author
    if author:
        sessions = sessions.filter(space__author__slug=author)
    return sessions


def get_upcoming_sessions_for_spaces_list():
    """Get all upcoming events for spaces listing, including spaces with full events.

    Specifically designed for the spaces list API endpoint.
    Does NOT filter by seat availability, ensuring all spaces with upcoming events are shown.
    """
    first_category_subquery = SpaceCategory.objects.filter(space=OuterRef("space_id")).values("name")[:1]
    return (
        Session.objects.filter(start__gte=timezone.now(), cancelled=False, listed=True, space__published=True)
        .select_related("space")
        .prefetch_related("space__author", "space__categories", "space__subscribed")
        .annotate(
            attendee_count=Count("attendees", distinct=True),
            subscriber_count=Count("space__subscribed", distinct=True),
            first_category=Subquery(first_category_subquery),
        )
        .order_by("start")
    )


def all_upcoming_recommended_spaces(user: User | None, category: str | None = None):
    sessions = Session.objects.filter(start__gte=timezone.now(), cancelled=False, open=True, listed=True)
    sessions = sessions.order_by("start")
    if not user or not user.is_staff:
        sessions = sessions.filter(space__published=True)
    # are there any seats?
    sessions = sessions.annotate(attendee_count=Count("attendees")).filter(attendee_count__lt=F("seats"))
    # filter category
    if category:
        sessions = sessions.filter(space__categories__slug=category) | sessions.filter(space__categories__name=category)
    sessions = sessions.prefetch_related("space__author")
    return sessions


def upcoming_attending_sessions(user: User, limit: int = 10):
    # 60 minutes in the past
    past = timezone.now() - datetime.timedelta(minutes=60)
    return user.sessions_attending.filter(start__gte=past).filter(cancelled=False).order_by("start")[:limit]


def upcoming_sessions_by_author(user: User, author: User, exclude_event: Session | None = None):
    upcoming_sessions = Session.objects.filter(
        space__author=author,
        start__gt=timezone.now(),
        cancelled=False,
        listed=True,
    ).order_by("start")

    if not user or not user.is_staff:
        upcoming_sessions = upcoming_sessions.filter(space__published=True)

    if exclude_event:
        upcoming_sessions = upcoming_sessions.exclude(pk=exclude_event.pk)

    upcoming_sessions = upcoming_sessions.select_related("space__author")
    return upcoming_sessions


def session_detail_schema(session: Session, user: User):
    space: Space = session.space
    start = session.start
    subscribed = space.subscribed.contains(user) if user.is_authenticated else None
    ended = session.ended()

    attending = session.attendees.filter(pk=user.pk).exists()

    return SessionDetailSchema(
        slug=session.slug,
        title=session.title,
        space_title=space.title,
        space=SessionSpaceSchema.from_orm(space),
        description=session.content_html,
        price=space.price,
        seats_left=session.seats_left(),
        duration=session.duration_minutes,
        recurring=space.recurring,
        subscribers=space.subscribed.count(),
        start=start,
        attending=attending,
        open=session.open,
        started=session.started(),
        cancelled=session.cancelled,
        joinable=session.can_join(user),
        ended=ended,
        rsvp_url=reverse("spaces:rsvp", kwargs={"session_slug": session.slug}),
        join_url=reverse("spaces:join", kwargs={"session_slug": session.slug}),
        cal_link=session.cal_link(),
        subscribe_url=reverse("mobile-api:spaces_subscribe", kwargs={"space_slug": space.slug}),
        subscribed=subscribed,
        user_timezone=str("UTC"),
        meeting_provider=space.meeting_provider,
    )


def space_detail_schema(space: Space, user: User, session: Session | None = None):
    category = space.categories.first()
    category_name = category.name if category else None

    next_session = session or space.next_session()
    next_session_schema: NextSessionSchema | None = None
    if next_session:
        seats_left = next_session.seats_left()
        next_session_schema = NextSessionSchema(
            slug=next_session.slug,
            start=next_session.start,
            title=next_session.title,
            link=next_session.get_absolute_url(),
            seats_left=seats_left,
            duration=next_session.duration_minutes,
            meeting_provider=next_session.space.meeting_provider,
            cal_link=next_session.cal_link(),
            attending=next_session.attendees.filter(pk=user.pk).exists(),
            cancelled=next_session.cancelled,
            open=next_session.open,
            joinable=next_session.can_join(user),
        )

    return SpaceDetailSchema(
        slug=space.slug,
        title=space.title,
        image_link=space.image.url if space.image else None,
        short_description=space.short_description,
        content=space.content_html,
        author=space.author,
        category=category_name,
        next_event=next_session_schema,
        subscribers=space.subscribed.count(),
        price=space.price,
        recurring=space.recurring,
    )
