import datetime
from dataclasses import dataclass

from django.db.models import Count, F, OuterRef, Q, Subquery
from django.urls import reverse
from django.utils import timezone

from totem.onboard.models import OnboardModel
from totem.spaces.mobile_api.mobile_filters import get_upcoming_spaces_list, upcoming_recommended_spaces
from totem.spaces.schemas import (
    NextSessionSchema,
    SessionDetailSchema,
    SessionSpaceSchema,
    SpaceDetailSchema,
    UpcomingSessionSchema,
)
from totem.users.models import User

from .models import Session, Space, SpaceCategory, exclude_banned_sessions


def other_sessions_in_space(user: User | None, session: Session, limit: int = 10):
    sessions = Session.objects.filter(space=session.space, start__gte=timezone.now(), cancelled=False).distinct()
    if user and user.is_authenticated:
        # show users events they are already attending
        sessions = sessions.filter(Q(open=True, listed=True) | Q(attendees=user))
    else:
        sessions = sessions.filter(open=True, listed=True)
    sessions = sessions.exclude(slug=session.slug)
    sessions = exclude_banned_sessions(sessions, user)
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
    sessions = exclude_banned_sessions(sessions, user)
    sessions = sessions.order_by("start")
    if not user or not user.is_staff:
        sessions = sessions.filter(space__published=True)
    return sessions


def all_upcoming_recommended_sessions(user: User | None, category: str | None = None, author: str | None = None):
    # Sessions stay listed until they end (even when full) so attendees can find them.
    sessions = Session.objects.filter(cancelled=False, listed=True).not_ended()
    sessions = exclude_banned_sessions(sessions, user)
    sessions = sessions.order_by("start")
    if not user or not user.is_staff:
        sessions = sessions.filter(space__published=True)
    # filter category
    if category:
        sessions = sessions.filter(space__categories__slug=category) | sessions.filter(space__categories__name=category)
    # filter author
    if author:
        sessions = sessions.filter(space__author__slug=author)
    sessions = sessions.prefetch_related("space__author")
    return sessions


def get_upcoming_sessions_for_spaces_list(user: User | None = None):
    """Get all upcoming events for spaces listing, including spaces with full events.

    Specifically designed for the spaces list API endpoint.
    Does NOT filter by seat availability, ensuring all spaces with upcoming events are shown.
    """
    first_category_subquery = SpaceCategory.objects.filter(space=OuterRef("space_id")).values("name")[:1]
    sessions = Session.objects.filter(cancelled=False, listed=True, space__published=True).not_ended()
    return (
        exclude_banned_sessions(sessions, user)
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
    sessions = exclude_banned_sessions(sessions, user)
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
    sessions = user.sessions_attending.filter(start__gte=past).filter(cancelled=False)
    return exclude_banned_sessions(sessions, user).order_by("start")[:limit]


def upcoming_sessions_by_author(user: User, author: User, exclude_event: Session | None = None):
    upcoming_sessions = (
        Session.objects.filter(
            space__author=author,
            cancelled=False,
            listed=True,
        )
        .not_ended()
        .order_by("start")
    )

    if not user or not user.is_staff:
        upcoming_sessions = upcoming_sessions.filter(space__published=True)

    if exclude_event:
        upcoming_sessions = upcoming_sessions.exclude(pk=exclude_event.pk)

    upcoming_sessions = exclude_banned_sessions(upcoming_sessions, user)
    upcoming_sessions = upcoming_sessions.select_related("space__author")
    return upcoming_sessions


@dataclass
class SpacesSummary:
    upcoming: list[Session]
    for_you: list[Space]
    explore: list[Space]


def spaces_summary_data(user: User) -> SpacesSummary:
    """The user's summary: registered sessions plus personalized and general recommendations.

    Shared by the web and mobile summary endpoints, which map it to their own schemas.
    """
    spaces_qs = get_upcoming_spaces_list(user)

    # Sessions the user has registered for that haven't ended yet.
    upcoming_sessions = (
        exclude_banned_sessions(
            Session.objects.filter(attendees=user, cancelled=False).not_ended(),
            user,
        )
        .select_related("space")
        .prefetch_related("space__author", "space__categories", "attendees", "joined", "space__subscribed")
        .annotate(
            attendee_count=Count("attendees", distinct=True),
            subscriber_count=Count("space__subscribed", distinct=True),
        )
        .order_by("start")
    )
    upcoming = list(upcoming_sessions)
    upcoming_space_slugs = {session.space.slug for session in upcoming}

    # Personalization signal: onboarding hopes plus categories of subscribed spaces.
    categories_set: set[str] = set()
    try:
        onboard_model = OnboardModel.objects.get(user=user)
        if onboard_model.hopes:
            for hope in onboard_model.hopes.split(","):
                name = hope.strip()
                if name:
                    categories_set.add(name)
    except OnboardModel.DoesNotExist:
        pass
    previous_category_names = spaces_qs.filter(subscribed=user).values_list("categories__name", flat=True).distinct()
    categories_set.update(name for name in previous_category_names if name)

    for_you = [
        space
        for space in upcoming_recommended_spaces(user, categories=list(categories_set))
        if space.slug not in upcoming_space_slugs
    ]
    explore = [space for space in spaces_qs if space.slug not in upcoming_space_slugs]
    return SpacesSummary(upcoming=upcoming, for_you=for_you, explore=explore)


def _next_session_schema(user: User, session: Session) -> UpcomingSessionSchema | None:
    upcoming = list(other_sessions_in_space(user, session, limit=1))
    if not upcoming:
        return None
    return UpcomingSessionSchema(
        slug=upcoming[0].slug,
        start=upcoming[0].start,
        link=upcoming[0].get_absolute_url(),
    )


def session_detail_schema(session: Session, user: User):
    space: Space = session.space
    start = session.start
    subscribed = space.subscribed.contains(user) if user.is_authenticated else None
    started = session.started()
    ended = session.ended()

    attending = session.attendees.filter(pk=user.pk).exists()
    join_opens_at, join_closes_at = session.join_window(user)

    # When this session can no longer be attended, point people at the
    # space's next one.
    next_session = None
    if started or ended or session.seats_left() <= 0:
        next_session = _next_session_schema(user, session)

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
        join_opens_at=join_opens_at,
        join_closes_at=join_closes_at,
        ends_at=session.end(),
        attending=attending,
        open=session.open,
        started=started,
        cancelled=session.cancelled,
        joinable=session.can_join(user),
        ended=ended,
        next_session=next_session,
        rsvp_url=reverse("spaces:rsvp", kwargs={"session_slug": session.slug}),
        join_url=reverse("spaces:join", kwargs={"session_slug": session.slug}),
        cal_link=session.cal_link(),
        subscribe_url=reverse("mobile-api:spaces_subscribe", kwargs={"space_slug": space.slug}),
        subscribed=subscribed,
        user_timezone=str("UTC"),
        meeting_provider=space.meeting_provider,
    )


def space_detail_schema(space: Space, user: User, session: Session | None = None):
    # These use the caches on querysets like get_upcoming_spaces_list (prefetched
    # categories/subscribed/upcoming_sessions, annotated subscriber_count) and
    # fall back to per-space queries for callers without them.
    categories = list(space.categories.all())
    category_name = categories[0].name if categories else None

    next_session = session
    if next_session is None:
        if hasattr(space, "upcoming_sessions"):
            upcoming: list[Session] = space.upcoming_sessions  # type: ignore[attr-defined]
            next_session = upcoming[0] if upcoming else None
        else:
            next_session = space.next_session(user)
    next_session_schema: NextSessionSchema | None = None
    if next_session:
        next_session_schema = NextSessionSchema(
            slug=next_session.slug,
            start=next_session.start,
            ends_at=next_session.end(),
            title=next_session.title,
            link=next_session.get_absolute_url(),
            seats_left=next_session.seats_left(),
            duration=next_session.duration_minutes,
            meeting_provider=next_session.space.meeting_provider,
            cal_link=next_session.cal_link(),
            rsvp_url=reverse("spaces:rsvp", kwargs={"session_slug": next_session.slug}),
            attending=user in next_session.attendees.all(),
            cancelled=next_session.cancelled,
            open=next_session.open,
            joinable=next_session.can_join(user),
        )

    if hasattr(space, "subscriber_count"):
        subscribers = space.subscriber_count  # type: ignore[attr-defined]
    else:
        subscribers = space.subscribed.count()

    return SpaceDetailSchema(
        slug=space.slug,
        title=space.title,
        image_link=space.image.url if space.image else None,
        short_description=space.short_description,
        content=space.content_html,
        author=space.author,
        category=category_name,
        next_event=next_session_schema,
        subscribers=subscribers,
        price=space.price,
        recurring=space.recurring,
    )
