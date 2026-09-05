from django.db.models import Count, F, Prefetch, Q
from django.urls import reverse
from django.utils import timezone

from totem.spaces.filters import author_circle_count_prefetch, upcoming_sessions_queryset
from totem.spaces.mobile_api.mobile_schemas import (
    MobileSpaceDetailSchema,
    NextSessionSchema,
    SessionDetailSchema,
)
from totem.spaces.models import Session, Space
from totem.users.models import User


def upcoming_recommended_sessions(user: User | None, categories: list[str] | None = None, author: str | None = None):
    # Annotate before visible_to: filtering on a multi-valued relation
    # (attendees) before annotating would constrain the Count to the
    # filtered rows.
    events = (
        Session.objects.annotate(attendee_count=Count("attendees", distinct=True))
        .filter(attendee_count__lt=F("seats"))
        .visible_to(user)
        .filter(start__gte=timezone.now())
        .select_related("space")
        .prefetch_related(
            "attendees",
            "joined",
            "space__author",
            author_circle_count_prefetch("space__author"),
            "space__categories",
            "space__subscribed",
            Prefetch(
                "space__sessions",
                queryset=upcoming_sessions_queryset(user),
                to_attr="upcoming_sessions",
            ),
        )
    )
    if categories:
        events = events.filter(Q(space__categories__slug__in=categories) | Q(space__categories__name__in=categories))
    if author:
        events = events.filter(space__author__slug=author)
    return events.distinct().order_by("start")


def session_detail_schema(session: Session, user: User):
    space: Space = session.space
    start = session.start

    if user.is_authenticated:
        if hasattr(space, "_prefetched_objects_cache") and "subscribed" in space._prefetched_objects_cache:
            subscribed = any(sub.pk == user.pk for sub in space.subscribed.all())
        else:
            subscribed = space.subscribed.filter(pk=user.pk).exists()
    else:
        subscribed = None
    ended = session.ended()

    if hasattr(session, "_prefetched_objects_cache") and "attendees" in session._prefetched_objects_cache:
        attending = any(attendee.pk == user.pk for attendee in session.attendees.all())
    else:
        attending = session.attendees.filter(pk=user.pk).exists()

    return SessionDetailSchema(
        slug=session.slug,
        title=session.title,
        space=space_detail_schema(space, user),
        content=session.content_html,
        seats_left=session.seats_left(),
        duration=session.duration_minutes,
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


def next_session_schema(next_session: Session, user: User):
    seats_left = next_session.seats_left()

    if hasattr(next_session, "_prefetched_objects_cache") and "attendees" in next_session._prefetched_objects_cache:
        attending = any(attendee.pk == user.pk for attendee in next_session.attendees.all())
    else:
        attending = next_session.attendees.filter(pk=user.pk).exists()

    return NextSessionSchema(
        slug=next_session.slug,
        start=next_session.start,
        title=next_session.title,
        link=next_session.get_absolute_url(),
        seats_left=seats_left,
        duration=next_session.duration_minutes,
        meeting_provider=next_session.space.meeting_provider,
        cal_link=next_session.cal_link(),
        attending=attending,
        cancelled=next_session.cancelled,
        open=next_session.open,
        joinable=next_session.can_join(user),
    )


def space_detail_schema(space: Space, user: User):
    if hasattr(space, "_prefetched_objects_cache") and "categories" in space._prefetched_objects_cache:
        category = min(space.categories.all(), key=lambda item: item.pk, default=None)
    else:
        category = space.categories.first()
    category_name = category.name if category else None

    if hasattr(space, "upcoming_sessions"):
        upcoming_sessions = space.upcoming_sessions
    else:
        upcoming_sessions = upcoming_sessions_queryset(user).filter(space=space)

    next_events = [next_session_schema(event, user) for event in upcoming_sessions]

    if hasattr(space, "subscriber_count"):
        subscribers = space.subscriber_count
    else:
        subscribers = space.subscribed.count()

    return MobileSpaceDetailSchema(
        slug=space.slug,
        title=space.title,
        image_link=space.image.url if space.image else None,
        short_description=space.short_description,
        content=space.content_html,
        author=space.author,
        category=category_name,
        subscribers=subscribers,
        price=space.price,
        recurring=space.recurring,
        next_events=next_events,
    )
