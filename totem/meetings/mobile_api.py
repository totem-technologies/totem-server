import logging

from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404
from ninja import Router
from ninja.errors import AuthorizationError

import totem.meetings.livekit_provider as livekit
from totem.circles.models import CircleEvent
from totem.meetings.schemas import LivekitMuteParticipantSchema, LivekitTokenResponseSchema
from totem.users import analytics
from totem.users.models import User

meetings_router = Router(
    tags=["meetings"],
)


@meetings_router.get(
    "/event/{event_slug}/token",
    response={200: LivekitTokenResponseSchema, 403: str, 404: str},
    url_name="get_livekit_token",
)
def get_livekit_token(request: HttpRequest, event_slug: str):
    user: User = request.user  # type: ignore

    try:
        event = CircleEvent.objects.get(slug=event_slug)
    except CircleEvent.DoesNotExist:
        return 404, "Session not found"

    is_joinable = event.can_join(user=user)
    if not is_joinable:
        logging.warning("User %s attempted to join non-joinable event %s", user.slug, event.slug)
        return 403, "Session is not joinable at this time."

    # Initialize the room with the speaking order if not already done
    speaking_order = event.attendees.all()
    livekit.initialize_room(event.slug, [attendee.slug for attendee in speaking_order])

    # Create and return the access token
    token = livekit.create_access_token(user, event)

    # Record that the user has joined the event
    event.joined.add(user)
    analytics.event_joined(user, event)

    return LivekitTokenResponseSchema(token=token)


@meetings_router.post(
    "/event/{event_slug}/pass-totem",
    url_name="pass_totem",
)
def pass_totem_endpoint(request: HttpRequest, event_slug: str):
    user: User = request.user  # type: ignore
    event: CircleEvent = get_object_or_404(CircleEvent, slug=event_slug)

    try:
        livekit.pass_totem(event_slug, event.circle.author.slug, user.slug)
        return HttpResponse()
    except ValueError as e:
        raise AuthorizationError(message=str(e))


@meetings_router.post(
    "/event/{event_slug}/accept-totem",
    url_name="accept_totem",
)
def accept_totem_endpoint(request: HttpRequest, event_slug: str):
    user: User = request.user  # type: ignore
    event: CircleEvent = get_object_or_404(CircleEvent, slug=event_slug)

    try:
        livekit.accept_totem(
            room_name=event_slug,
            user_identity=user.slug,
            keeper_slug=event.circle.author.slug,
        )
        return HttpResponse()
    except ValueError as e:
        raise AuthorizationError(message=str(e))


@meetings_router.post(
    "/event/{event_slug}/start",
    url_name="start_room",
)
def start_room_endpoint(request: HttpRequest, event_slug: str):
    user: User = request.user  # type: ignore
    event: CircleEvent = get_object_or_404(CircleEvent, slug=event_slug)
    is_keeper = event.circle.author.slug == user.slug

    if not is_keeper:
        logging.warning("User %s attempted to update metadata for event %s", user.slug, event.slug)
        raise AuthorizationError(message="Only the Keeper can update room metadata.")

    try:
        livekit.start_room(room_name=event.slug, keeper_slug=event.circle.author.slug)
        return HttpResponse()
    except ValueError as e:
        raise AuthorizationError(message=str(e))


@meetings_router.post(
    "/event/{event_slug}/end",
    url_name="end_room",
)
def end_room_endpoint(request: HttpRequest, event_slug: str):
    user: User = request.user  # type: ignore
    event: CircleEvent = get_object_or_404(CircleEvent, slug=event_slug)
    is_keeper = event.circle.author.slug == user.slug

    if not is_keeper:
        logging.warning("User %s attempted to update metadata for event %s", user.slug, event.slug)
        raise AuthorizationError(message="Only the Keeper can update room metadata.")

    try:
        livekit.end_room(event.slug)
        return HttpResponse()
    except ValueError as e:
        raise Http404(str(e))


@meetings_router.post(
    "/event/{event_slug}/mute/{participant_identity}",
    url_name="mute_participant",
)
def mute_participant_endpoint(request: HttpRequest, event_slug: str, participant_identity: str):
    user: User = request.user  # type: ignore
    event: CircleEvent = get_object_or_404(CircleEvent, slug=event_slug)
    is_keeper = event.circle.author.slug == user.slug

    if not is_keeper:
        logging.warning("User %s attempted to update metadata for event %s", user.slug, event_slug)
        raise AuthorizationError(message="Only the Keeper can update room metadata.")

    try:
        livekit.mute_participant(event.slug, participant_identity)
        return HttpResponse()
    except ValueError as e:
        raise Http404(str(e))


@meetings_router.post(
    "/event/{event_slug}/remove/{participant_identity}",
    url_name="remove_participant",
)
def remove_participant_endpoint(request: HttpRequest, event_slug: str, participant_identity: str):
    user: User = request.user  # type: ignore
    event: CircleEvent = get_object_or_404(CircleEvent, slug=event_slug)
    is_keeper = event.circle.author.slug == user.slug

    if not is_keeper:
        logging.warning("User %s attempted to update metadata for event %s", user.slug, event_slug)
        raise AuthorizationError(message="Only the Keeper can update room metadata.")

    if event.circle.author.slug == participant_identity:
        raise AuthorizationError(message="Cannot remove the keeper from the room.")

    try:
        livekit.remove_participant(event.slug, participant_identity)
        return HttpResponse()
    except ValueError:
        raise Http404("Failed to remove participant")


@meetings_router.post(
    "/event/{event_slug}/reorder",
    response={200: LivekitMuteParticipantSchema, 404: str},
    url_name="reorder_participants",
)
def reorder_participants_endpoint(request: HttpRequest, event_slug: str, order: LivekitMuteParticipantSchema):
    user: User = request.user  # type: ignore
    event: CircleEvent = get_object_or_404(CircleEvent, slug=event_slug)
    is_keeper = event.circle.author.slug == user.slug

    if not is_keeper:
        logging.warning("User %s attempted to update metadata for event %s", user.slug, event_slug)
        raise AuthorizationError(message="Only the Keeper can update room metadata.")

    try:
        new_order = livekit.reorder(event.slug, order.order)
        return LivekitMuteParticipantSchema(order=new_order)
    except ValueError:
        raise Http404(f"Event {event_slug} not found or has already ended.")
