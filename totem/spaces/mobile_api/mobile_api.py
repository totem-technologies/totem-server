from django.db import transaction
from django.db.models import Prefetch
from django.http import Http404, HttpRequest
from django.shortcuts import get_object_or_404
from ninja import Query, Router, Status
from ninja.errors import AuthorizationError
from ninja.pagination import paginate

from totem.spaces.filters import get_upcoming_spaces_list, spaces_summary_data, upcoming_sessions_queryset
from totem.spaces.mobile_api.mobile_filters import (
    session_detail_schema,
    space_detail_schema,
    upcoming_recommended_sessions,
)
from totem.spaces.mobile_api.mobile_schemas import (
    MobileSpaceDetailSchema,
    SessionDetailSchema,
    SessionFeedbackSchema,
    SpaceSchema,
    SummarySpacesSchema,
    SwitchSessionSchema,
)
from totem.spaces.models import (
    Session,
    SessionException,
    SessionFeedback,
    SessionFeedbackOptions,
    SessionTimeConflict,
    Space,
)
from totem.users.models import User

spaces_router = Router(tags=["spaces"])


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
    response={200: SessionDetailSchema, 409: SessionDetailSchema},
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
            session.add_attendee(user)
            session.space.subscribe(user)
    except SessionTimeConflict as e:
        return Status(409, session_detail_schema(e.conflicting_session, user))
    except SessionException as e:
        raise AuthorizationError(message=str(e))
    return session_detail_schema(session, user)


@spaces_router.post(
    "/rsvp/{event_slug}/switch",
    response={200: SessionDetailSchema, 409: SessionDetailSchema},
    tags=["spaces"],
    url_name="rsvp_switch",
)
def rsvp_switch(request: HttpRequest, event_slug: str, payload: SwitchSessionSchema):
    user: User = request.user  # type: ignore
    session = get_object_or_404(Session, slug=event_slug)
    if not session.can_view(user):
        raise Http404

    try:
        with transaction.atomic():
            locked_sessions = {
                item.slug: item
                for item in Session.objects.select_for_update()
                .select_related("space")
                .filter(slug__in=[event_slug, payload.conflicting_session_slug])
                .order_by("pk")
            }
            session = locked_sessions.get(event_slug)
            conflicting_session = locked_sessions.get(payload.conflicting_session_slug)
            if session is None or conflicting_session is None:
                raise Http404
            if not conflicting_session.can_view(user):
                raise Http404
            if not conflicting_session.attendees.filter(pk=user.pk).exists():
                raise Http404
            if not session.overlaps(conflicting_session):
                raise AuthorizationError(message="Sessions do not conflict")

            conflicting_sessions = []
            if not user.is_staff:
                conflicting_sessions = list(
                    session.time_conflicts_for(user).select_for_update().select_related("space").order_by("pk")
                )
            session.can_attend(user=user, excluding_time_conflicts=conflicting_sessions)
            for conflicting_session in conflicting_sessions:
                conflicting_session.remove_attendee(user)
            session.add_attendee(user)
            session.space.subscribe(user)
    except SessionTimeConflict as e:
        return Status(409, session_detail_schema(e.conflicting_session, user))
    except SessionException as e:
        raise AuthorizationError(message=str(e))
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
