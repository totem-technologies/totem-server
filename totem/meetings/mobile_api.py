import logging

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from ninja import Router
from ninja.errors import AuthorizationError

import totem.meetings.livekit_provider as livekit
from totem.circles.models import CircleEvent
from totem.meetings.schemas import LivekitTokenResponseSchema
from totem.users import analytics
from totem.users.models import User

meetings_router = Router()


@meetings_router.get(
    "/event/{event_slug}/token",
    response={200: LivekitTokenResponseSchema, 403: str, 404: str},
    tags=["meetings"],
    url_name="get_livekit_token",
)
def get_livekit_token(request, event_slug: str):
    user: User = request.auth

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
    tags=["meetings"],
    url_name="pass_totem",
)
def pass_totem_endpoint(request, event_slug: str):
    user: User = request.auth

    try:
        livekit.pass_totem(event_slug, user.slug)
        return HttpResponse()
    except ValueError as e:
        raise AuthorizationError(message=str(e))


@meetings_router.post(
    "/event/{event_slug}/start",
    tags=["meetings"],
    url_name="start_room",
)
def start_room_endpoint(request, event_slug: str):
    user: User = request.auth
    event: CircleEvent = get_object_or_404(CircleEvent, slug=event_slug)

    if not user.is_staff:
        logging.warning("User %s attempted to update metadata for event %s", user.slug, event.slug)
        raise AuthorizationError(message="Only staff can update room metadata.")

    try:
        livekit.start_room(event.slug)
        return HttpResponse()
    except ValueError as e:
        raise AuthorizationError(message=str(e))


@meetings_router.post(
    "/event/{event_slug}/mute/{participant_identity}",
    tags=["meetings"],
    url_name="mute_participant",
)
def mute_participant_endpoint(request, event_slug: str, participant_identity: str):
    user: User = request.auth
    event: CircleEvent = get_object_or_404(CircleEvent, slug=event_slug)

    if not user.is_staff:
        logging.warning("User %s attempted to update metadata for event %s", user.slug, event.slug)
        raise AuthorizationError(message="Only staff can update room metadata.")

    try:
        livekit.mute_participant(event.slug, participant_identity)
        return HttpResponse()
    except ValueError as e:
        raise AuthorizationError(message=str(e))
