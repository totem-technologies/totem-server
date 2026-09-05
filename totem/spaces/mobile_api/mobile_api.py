from django.db import transaction
from django.db.models import Prefetch, prefetch_related_objects
from django.http import Http404, HttpRequest
from django.shortcuts import get_object_or_404
from ninja import Query, Router, Status
from ninja.errors import AuthorizationError
from ninja.pagination import paginate

from totem.spaces.filters import (
    author_circle_count_prefetch,
    get_upcoming_spaces_list,
    spaces_summary_data,
    upcoming_sessions_queryset,
)
from totem.spaces.mobile_api.mobile_filters import (
    session_detail_schema,
    space_detail_schema,
    upcoming_recommended_sessions,
)
from totem.spaces.mobile_api.mobile_schemas import (
    MobileSpaceDetailSchema,
    ResolveConflictsSchema,
    SessionConflictSchema,
    SessionDetailSchema,
    SessionFeedbackSchema,
    SpaceSchema,
    SummarySpacesSchema,
)
from totem.spaces.models import (
    Session,
    SessionException,
    SessionFeedback,
    SessionFeedbackOptions,
    SessionTimeConflict,
    Space,
)
from totem.spaces.rsvp import resolve_session_conflicts
from totem.users.models import User

spaces_router = Router(tags=["spaces"])


def _prefetch_session_detail_relations(sessions: list[Session], user: User) -> None:
    upcoming_sessions = upcoming_sessions_queryset(user).prefetch_related("joined")
    prefetch_related_objects(
        sessions,
        "attendees",
        "joined",
        author_circle_count_prefetch("space__author"),
        "space__categories",
        "space__subscribed",
        Prefetch("space__sessions", queryset=upcoming_sessions, to_attr="upcoming_sessions"),
    )


def _session_conflict_schema(conflicting_sessions: list[Session], user: User) -> SessionConflictSchema:
    _prefetch_session_detail_relations(conflicting_sessions, user)
    return SessionConflictSchema(
        message=SessionTimeConflict.message,
        conflicting_sessions=[session_detail_schema(conflict, user) for conflict in conflicting_sessions],
    )


@spaces_router.post("/subscribe/{space_slug}", response={200: bool}, url_name="spaces_subscribe")
def subscribe_to_space(request: HttpRequest, space_slug: str):
    space = get_object_or_404(Space, slug=space_slug, published=True)
    space.subscribe(request.user)
    return True


@spaces_router.delete("/subscribe/{space_slug}", response={200: bool}, url_name="spaces_unsubscribe")
def unsubscribe_to_space(request: HttpRequest, space_slug: str):
    space = get_object_or_404(Space, slug=space_slug)
    space.unsubscribe(request.user)
    return True


@spaces_router.get("/subscribe", response={200: list[SpaceSchema]}, url_name="spaces_subscriptions")
def list_subscriptions(request: HttpRequest):
    return Space.objects.filter(subscribed=request.user)


@spaces_router.get("/", response={200: list[MobileSpaceDetailSchema]}, url_name="mobile_spaces_list")
@paginate
def list_spaces(request):
    user: User = request.user  # type: ignore
    spaces = get_upcoming_spaces_list(user)
    return [space_detail_schema(space, user) for space in spaces]


@spaces_router.get("/space/{space_slug}", response={200: MobileSpaceDetailSchema}, url_name="spaces_detail")
def get_space_detail(request: HttpRequest, space_slug: str):
    user: User = request.user  # type: ignore
    space = get_object_or_404(
        Space.objects.prefetch_related(
            Prefetch("sessions", queryset=upcoming_sessions_queryset(user), to_attr="upcoming_sessions"),
        ),
        slug=space_slug,
    )
    if not space.can_view(user):
        raise Http404
    return space_detail_schema(space, user)


@spaces_router.get("/keeper/{slug}/", response={200: list[MobileSpaceDetailSchema]}, url_name="keeper_spaces")
def get_keeper_spaces(request: HttpRequest, slug: str):
    user: User = request.user  # type: ignore
    spaces = get_upcoming_spaces_list(user, author_slug=slug)
    return [space_detail_schema(space, user) for space in spaces]


@spaces_router.get("/session/{event_slug}", response={200: SessionDetailSchema}, url_name="session_detail")
def get_session_detail(request: HttpRequest, event_slug: str):
    user: User = request.user  # type: ignore
    session = get_object_or_404(
        Session.objects.select_related("space").prefetch_related(
            Prefetch("space__sessions", queryset=upcoming_sessions_queryset(user), to_attr="upcoming_sessions"),
        ),
        slug=event_slug,
    )
    if not session.can_view(user):
        raise Http404
    return session_detail_schema(session, user)


@spaces_router.post("/session/{event_slug}/feedback", response={204: None}, url_name="session_feedback")
def post_session_feedback(request: HttpRequest, event_slug: str, payload: SessionFeedbackSchema):
    user: User = request.user  # type: ignore
    session = get_object_or_404(Session, slug=event_slug)

    if not session.attendees.filter(pk=user.pk).exists():
        raise AuthorizationError(message="User is not an attendee of this event.")

    defaults: dict[str, str] = {"feedback": payload.feedback.value}
    if payload.feedback == SessionFeedbackOptions.DOWN:
        defaults["message"] = payload.message or ""
    else:
        defaults["message"] = ""

    SessionFeedback.objects.update_or_create(
        session=session,
        user=user,
        defaults=defaults,
    )

    return Status(204, None)


@spaces_router.get("/sessions/history", response={200: list[SessionDetailSchema]}, url_name="sessions_history")
def get_sessions_history(request: HttpRequest):
    user: User = request.user  # type: ignore

    session_history = Session.objects.history_for(user)[0:10]
    return [session_detail_schema(session, user) for session in session_history]


@spaces_router.get("/sessions/recommended", response={200: list[SessionDetailSchema]}, url_name="recommended_spaces")
def get_recommended_spaces(request: HttpRequest, limit: int = 3, categories: list[str] | None = Query(None)):
    user: User = request.user  # type: ignore

    recommended_sessions = upcoming_recommended_sessions(user, categories=categories)[:limit]

    sessions = [session_detail_schema(session, user) for session in recommended_sessions]
    return sessions


@spaces_router.get(
    "/summary",
    response={200: SummarySpacesSchema},
    tags=["spaces"],
    url_name="spaces_summary",
)
def get_spaces_summary(request: HttpRequest):
    user: User = request.user  # type: ignore
    data = spaces_summary_data(user)
    return SummarySpacesSchema(
        upcoming=[session_detail_schema(session, user) for session in data.upcoming],
        for_you=[space_detail_schema(space, user) for space in data.for_you],
        explore=[space_detail_schema(space, user) for space in data.explore],
    )


@spaces_router.post(
    "/rsvp/{event_slug}",
    response={200: SessionDetailSchema, 409: SessionConflictSchema},
    tags=["spaces"],
    url_name="rsvp_confirm",
)
def rsvp_confirm(request: HttpRequest, event_slug: str):
    user: User = request.user  # type: ignore
    session = get_object_or_404(Session, slug=event_slug)
    if not session.can_view(user):
        raise Http404
    try:
        with transaction.atomic():
            if not session.add_attendee(user):
                raise SessionException("Unable to save your spot")
            session.space.subscribe(user)
    except SessionTimeConflict as e:
        return Status(409, _session_conflict_schema(e.conflicting_sessions, user))
    except SessionException as e:
        raise AuthorizationError(message=str(e))
    return session_detail_schema(session, user)


@spaces_router.post(
    "/rsvp/{event_slug}/resolve-conflicts",
    response={200: SessionDetailSchema, 409: SessionConflictSchema},
    tags=["spaces"],
    url_name="rsvp_resolve_conflicts",
)
def rsvp_resolve_conflicts(request: HttpRequest, event_slug: str, payload: ResolveConflictsSchema):
    user: User = request.user  # type: ignore
    session = get_object_or_404(
        Session.objects.select_related("space", "space__author", "room").prefetch_related("attendees"),
        slug=event_slug,
    )
    if not session.can_view(user):
        raise Http404

    try:
        resolve_session_conflicts(session, user, payload.conflicting_session_slugs)
    except SessionTimeConflict as e:
        return Status(409, _session_conflict_schema(e.conflicting_sessions, user))
    except SessionException as e:
        raise AuthorizationError(message=str(e))
    _prefetch_session_detail_relations([session], user)
    return session_detail_schema(session, user)


@spaces_router.delete(
    "/rsvp/{event_slug}",
    response={200: SessionDetailSchema},
    tags=["spaces"],
    url_name="rsvp_cancel",
)
def rsvp_cancel(request: HttpRequest, event_slug: str):
    user: User = request.user  # type: ignore
    session = get_object_or_404(Session, slug=event_slug)
    if not session.can_view(user):
        raise Http404
    try:
        session.remove_attendee(user)
    except SessionException as e:
        raise AuthorizationError(message=str(e))
    return session_detail_schema(session, user)
