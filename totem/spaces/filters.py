import datetime
from dataclasses import dataclass

from django.db.models import Count, Exists, OuterRef, Prefetch, Q, prefetch_related_objects
from django.urls import reverse
from django.utils import timezone

from totem.onboard.models import OnboardModel
from totem.spaces.schemas import (
    NextSessionSchema,
    SessionConflictSchema,
    SessionDetailSchema,
    SessionSpaceSchema,
    SpaceDetailSchema,
    UpcomingSessionSchema,
)
from totem.users.models import User

from .models import Session, SessionQuerySet, SessionTimeConflict, Space


def upcoming_sessions_queryset(user: User | None = None) -> SessionQuerySet:
    """A space's upcoming sessions as shown to this user, soonest first.

    Sessions stay visible until they end (even when full) so attendees can
    find them.
    """
    return Session.objects.visible_to(user).not_ended().order_by("start").prefetch_related("attendees")


def get_upcoming_spaces_list(
    user: User | None = None,
    categories: list[str] | None = None,
    author_slug: str | None = None,
) -> list[Space]:
    """Spaces with at least one visible upcoming session, soonest first.

    A space's position, its card, and its next sessions all derive from the
    same prefetched upcoming_sessions list, so ordering and display cannot
    disagree.
    """
    # The Exists filter and the prefetch share one queryset, so a space is
    # listed exactly when its upcoming_sessions list is non-empty.
    upcoming_sessions = upcoming_sessions_queryset(user)
    spaces = (
        Space.objects.filter(Exists(upcoming_sessions.filter(space=OuterRef("pk"))))
        .select_related("author")
        .prefetch_related(
            "categories",
            "subscribed",
            Prefetch("sessions", queryset=upcoming_sessions, to_attr="upcoming_sessions"),
        )
        .annotate(subscriber_count=Count("subscribed", distinct=True))
    )
    if not (user and user.is_authenticated and user.is_staff):
        spaces = spaces.filter(published=True)
    if categories:
        spaces = spaces.filter(Q(categories__slug__in=categories) | Q(categories__name__in=categories)).distinct()
    if author_slug:
        spaces = spaces.filter(author__slug=author_slug)
    upcoming: list[Space] = [space for space in spaces if space.upcoming_sessions]
    # Slug tiebreaker: sessions start on the hour, and the paginated mobile
    # list recomputes per page, so tied starts must order identically on
    # every request.
    upcoming.sort(key=lambda space: (space.upcoming_sessions[0].start, space.slug))  # type: ignore[attr-defined]
    return upcoming


def other_sessions_in_space(user: User | None, session: Session, limit: int = 10):
    return (
        Session.objects.visible_to(user)
        .open_to(user)
        .filter(space=session.space, start__gte=timezone.now())
        .exclude(slug=session.slug)
        .order_by("start")[:limit]
    )


def sessions_by_month(user: User | None, space_slug: str, month: int, year: int):
    start_date = datetime.datetime(year, month, 1, tzinfo=datetime.timezone.utc)
    end_date = start_date + datetime.timedelta(days=32)
    return (
        Session.objects.visible_to(user)
        .open_to(user)
        .filter(space__slug=space_slug, start__gte=start_date, start__lte=end_date)
        .order_by("start")
    )


def all_upcoming_recommended_sessions(user: User | None, category: str | None = None, author: str | None = None):
    sessions = Session.objects.visible_to(user).not_ended().order_by("start")
    if category:
        sessions = sessions.filter(Q(space__categories__slug=category) | Q(space__categories__name=category))
    if author:
        sessions = sessions.filter(space__author__slug=author)
    return sessions.prefetch_related("space__author")


def upcoming_attending_sessions(user: User, limit: int = 10):
    # Keep sessions for an hour after start so late joiners can still find them.
    past = timezone.now() - datetime.timedelta(minutes=60)
    return Session.objects.visible_to(user).filter(attendees=user, start__gte=past).order_by("start")[:limit]


def upcoming_sessions_by_author(user: User | None, author: User, exclude_event: Session | None = None):
    sessions = (
        Session.objects.visible_to(user)
        .filter(space__author=author)
        .not_ended()
        .order_by("start")
        .select_related("space__author")
    )
    if exclude_event:
        sessions = sessions.exclude(pk=exclude_event.pk)
    return sessions


@dataclass
class SpacesSummary:
    upcoming: list[Session]
    for_you: list[Space]
    explore: list[Space]


def spaces_summary_data(user: User) -> SpacesSummary:
    """The user's summary: registered sessions plus personalized and general recommendations.

    Shared by the web and mobile summary endpoints, which map it to their own schemas.
    """
    spaces = get_upcoming_spaces_list(user)

    # Sessions the user has registered for that haven't ended yet.
    upcoming = list(
        Session.objects.visible_to(user)
        .filter(attendees=user)
        .not_ended()
        .select_related("space")
        .prefetch_related("space__author", "space__categories", "attendees", "joined", "space__subscribed")
        .order_by("start")
    )
    upcoming_space_slugs = {session.space.slug for session in upcoming}

    # Personalization signal: onboarding hopes plus categories of subscribed
    # spaces (both prefetched, so no extra queries).
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
    for space in spaces:
        if any(sub.pk == user.pk for sub in space.subscribed.all()):
            categories_set.update(category.name for category in space.categories.all())

    # With no personalization signal yet, everything is "for you".
    def matches_interests(space: Space) -> bool:
        if not categories_set:
            return True
        return any(
            category.slug in categories_set or category.name in categories_set for category in space.categories.all()
        )

    for_you = [space for space in spaces if space.slug not in upcoming_space_slugs and matches_interests(space)]
    explore = [space for space in spaces if space.slug not in upcoming_space_slugs]
    return SpacesSummary(upcoming=upcoming, for_you=for_you, explore=explore)


def _next_session_schema(user: User, session: Session) -> UpcomingSessionSchema | None:
    if hasattr(session.space, "rsvp_next_sessions"):
        next_session = next(
            (candidate for candidate in session.space.rsvp_next_sessions if candidate.pk != session.pk),  # type: ignore[attr-defined]
            None,
        )
    else:
        upcoming = list(other_sessions_in_space(user, session, limit=1))
        next_session = upcoming[0] if upcoming else None
    if next_session is None:
        return None
    return UpcomingSessionSchema(
        slug=next_session.slug,
        start=next_session.start,
        link=next_session.get_absolute_url(),
    )


def session_detail_schema(session: Session, user: User, *, include_next_session: bool = True):
    space: Space = session.space
    start = session.start
    subscribed = space.subscribed.contains(user) if user.is_authenticated else None
    started = session.started()
    ended = session.ended()

    attending = session.attendees.contains(user) if user.is_authenticated else False
    join_opens_at, join_closes_at = session.join_window(user)

    # When this session can no longer be attended, point people at the
    # space's next one.
    next_session = None
    if include_next_session and (started or ended or session.seats_left() <= 0):
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


def prefetch_session_detail_relations(
    sessions: list[Session],
    user: User,
    *,
    include_next_sessions: bool = False,
) -> None:
    relations: list[str | Prefetch] = [
        "attendees",
        "joined",
        "space__author__sessions_joined",
        "space__categories",
        "space__subscribed",
    ]
    if include_next_sessions:
        next_sessions = (
            Session.objects.visible_to(user).open_to(user).filter(start__gte=timezone.now()).order_by("start")
        )
        relations.append(
            Prefetch(
                "space__sessions",
                queryset=next_sessions,
                to_attr="rsvp_next_sessions",
            )
        )
    prefetch_related_objects(sessions, *relations)


def session_conflict_schema(conflicting_sessions: list[Session], user: User) -> SessionConflictSchema:
    prefetch_session_detail_relations(conflicting_sessions, user)
    return SessionConflictSchema(
        message=SessionTimeConflict.message,
        conflicting_sessions=[
            session_detail_schema(conflict, user, include_next_session=False) for conflict in conflicting_sessions
        ],
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
