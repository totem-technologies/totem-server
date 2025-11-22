import logging

from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404
from livekit import api
from ninja import Router

import totem.meetings.livekit_provider as livekit
from totem.circles.models import CircleEvent
from totem.meetings.livekit_provider import (
    KeeperNotInRoomError,
    LiveKitConfigurationError,
    NoAudioTrackError,
    NotCurrentSpeakerError,
    ParticipantNotFoundError,
    RoomAlreadyEndedError,
    RoomAlreadyStartedError,
    RoomNotFoundError,
    UnauthorizedError,
)
from totem.meetings.room_state import SessionState
from totem.meetings.schemas import ErrorResponseSchema, LivekitMuteParticipantSchema, LivekitTokenResponseSchema
from totem.users import analytics
from totem.users.models import User

meetings_router = Router(
    tags=["meetings"],
)


@meetings_router.get(
    "/event/{event_slug}/token",
    response={
        200: LivekitTokenResponseSchema,
        403: ErrorResponseSchema,
        404: ErrorResponseSchema,
        500: ErrorResponseSchema,
    },
    url_name="get_livekit_token",
)
def get_livekit_token(request: HttpRequest, event_slug: str):
    user: User = request.user  # type: ignore

    try:
        event = CircleEvent.objects.get(slug=event_slug)
    except CircleEvent.DoesNotExist:
        return 404, ErrorResponseSchema(error="Session not found")

    is_joinable = event.can_join(user=user)
    if not is_joinable:
        logging.warning("User %s attempted to join non-joinable event %s", user.slug, event.slug)
        return 403, ErrorResponseSchema(error="Session is not joinable at this time.")

    try:
        # Initialize the room with the speaking order if not already done
        speaking_order = event.attendees.all()
        livekit.initialize_room(event.slug, [attendee.slug for attendee in speaking_order])

        # Create and return the access token
        token = livekit.create_access_token(user, event)

        # Record that the user has joined the event
        event.joined.add(user)
        analytics.event_joined(user, event)

        return LivekitTokenResponseSchema(token=token)
    except LiveKitConfigurationError as e:
        logging.error(f"LiveKit configuration error: {e}")
        return 500, ErrorResponseSchema(error="LiveKit service is not properly configured.")
    except api.TwirpError as e:
        logging.error(f"LiveKit API error in get_livekit_token: {e}")
        return 500, ErrorResponseSchema(error=f"Failed to create access token: {str(e)}")
    except Exception as e:
        logging.error(f"Unexpected error in get_livekit_token: {e}", exc_info=True)
        return 500, ErrorResponseSchema(error="An unexpected error occurred while creating access token.")


@meetings_router.post(
    "/event/{event_slug}/pass-totem",
    response={
        200: None,
        400: ErrorResponseSchema,
        403: ErrorResponseSchema,
        404: ErrorResponseSchema,
        500: ErrorResponseSchema,
    },
    url_name="pass_totem",
)
def pass_totem_endpoint(request: HttpRequest, event_slug: str):
    user: User = request.user  # type: ignore
    event: CircleEvent = get_object_or_404(CircleEvent, slug=event_slug)

    try:
        livekit.pass_totem(event_slug, event.circle.author.slug, user.slug)
        return HttpResponse(status=200)
    except RoomNotFoundError as e:
        return 404, ErrorResponseSchema(error=str(e))
    except KeeperNotInRoomError as e:
        return 404, ErrorResponseSchema(error=str(e))
    except UnauthorizedError as e:
        return 403, ErrorResponseSchema(error=str(e))
    except api.TwirpError as e:
        logging.error(f"LiveKit API error in pass_totem: {e}")
        return 500, ErrorResponseSchema(error=f"Failed to pass totem: {str(e)}")
    except Exception as e:
        logging.error(f"Unexpected error in pass_totem: {e}", exc_info=True)
        return 500, ErrorResponseSchema(error="An unexpected error occurred while passing the totem.")


@meetings_router.post(
    "/event/{event_slug}/accept-totem",
    response={
        200: None,
        400: ErrorResponseSchema,
        403: ErrorResponseSchema,
        404: ErrorResponseSchema,
        500: ErrorResponseSchema,
    },
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
        return HttpResponse(status=200)
    except RoomNotFoundError as e:
        return 404, ErrorResponseSchema(error=str(e))
    except KeeperNotInRoomError as e:
        return 404, ErrorResponseSchema(error=str(e))
    except NotCurrentSpeakerError as e:
        return 403, ErrorResponseSchema(error=str(e))
    except api.TwirpError as e:
        logging.error(f"LiveKit API error in accept_totem: {e}")
        return 500, ErrorResponseSchema(error=f"Failed to accept totem: {str(e)}")
    except Exception as e:
        logging.error(f"Unexpected error in accept_totem: {e}", exc_info=True)
        return 500, ErrorResponseSchema(error="An unexpected error occurred while accepting the totem.")


@meetings_router.post(
    "/event/{event_slug}/start",
    response={
        200: None,
        400: ErrorResponseSchema,
        403: ErrorResponseSchema,
        404: ErrorResponseSchema,
        500: ErrorResponseSchema,
    },
    url_name="start_room",
)
def start_room_endpoint(request: HttpRequest, event_slug: str):
    user: User = request.user  # type: ignore
    event: CircleEvent = get_object_or_404(CircleEvent, slug=event_slug)
    is_keeper = event.circle.author.slug == user.slug

    if not is_keeper:
        logging.warning("User %s attempted to start room for event %s", user.slug, event.slug)
        return 403, ErrorResponseSchema(error="Only the Keeper can start the room.")

    try:
        livekit.start_room(room_name=event.slug, keeper_slug=event.circle.author.slug)
        return HttpResponse(status=200)
    except RoomNotFoundError as e:
        return 404, ErrorResponseSchema(error=str(e))
    except KeeperNotInRoomError as e:
        return 404, ErrorResponseSchema(error=str(e))
    except RoomAlreadyStartedError as e:
        return 400, ErrorResponseSchema(error=str(e))
    except api.TwirpError as e:
        logging.error(f"LiveKit API error in start_room: {e}")
        return 500, ErrorResponseSchema(error=f"Failed to start room: {str(e)}")
    except Exception as e:
        logging.error(f"Unexpected error in start_room: {e}", exc_info=True)
        return 500, ErrorResponseSchema(error="An unexpected error occurred while starting the room.")


@meetings_router.post(
    "/event/{event_slug}/end",
    response={
        200: None,
        400: ErrorResponseSchema,
        403: ErrorResponseSchema,
        404: ErrorResponseSchema,
        500: ErrorResponseSchema,
    },
    url_name="end_room",
)
def end_room_endpoint(request: HttpRequest, event_slug: str):
    user: User = request.user  # type: ignore
    event: CircleEvent = get_object_or_404(CircleEvent, slug=event_slug)
    is_keeper = event.circle.author.slug == user.slug

    if not is_keeper:
        logging.warning("User %s attempted to end room for event %s", user.slug, event.slug)
        return 403, ErrorResponseSchema(error="Only the Keeper can end the room.")

    try:
        livekit.end_room(event.slug)
        return HttpResponse(status=200)
    except RoomNotFoundError as e:
        return 404, ErrorResponseSchema(error=str(e))
    except RoomAlreadyEndedError as e:
        return 400, ErrorResponseSchema(error=str(e))
    except api.TwirpError as e:
        logging.error(f"LiveKit API error in end_room: {e}")
        return 500, ErrorResponseSchema(error=f"Failed to end room: {str(e)}")
    except Exception as e:
        logging.error(f"Unexpected error in end_room: {e}", exc_info=True)
        return 500, ErrorResponseSchema(error="An unexpected error occurred while ending the room.")


@meetings_router.post(
    "/event/{event_slug}/mute/{participant_identity}",
    response={
        200: None,
        400: ErrorResponseSchema,
        403: ErrorResponseSchema,
        404: ErrorResponseSchema,
        500: ErrorResponseSchema,
    },
    url_name="mute_participant",
)
def mute_participant_endpoint(request: HttpRequest, event_slug: str, participant_identity: str):
    user: User = request.user  # type: ignore
    event: CircleEvent = get_object_or_404(CircleEvent, slug=event_slug)
    is_keeper = event.circle.author.slug == user.slug

    if not is_keeper:
        logging.warning("User %s attempted to mute participant in event %s", user.slug, event_slug)
        return 403, ErrorResponseSchema(error="Only the Keeper can mute participants.")

    try:
        livekit.mute_participant(event.slug, participant_identity)
        return HttpResponse(status=200)
    except ParticipantNotFoundError as e:
        return 404, ErrorResponseSchema(error=str(e))
    except NoAudioTrackError as e:
        return 400, ErrorResponseSchema(error=str(e))
    except api.TwirpError as e:
        logging.error(f"LiveKit API error in mute_participant: {e}")
        return 500, ErrorResponseSchema(error=f"Failed to mute participant: {str(e)}")
    except Exception as e:
        logging.error(f"Unexpected error in mute_participant: {e}", exc_info=True)
        return 500, ErrorResponseSchema(error="An unexpected error occurred while muting participant.")


@meetings_router.post(
    "/event/{event_slug}/remove/{participant_identity}",
    response={
        200: None,
        400: ErrorResponseSchema,
        403: ErrorResponseSchema,
        404: ErrorResponseSchema,
        500: ErrorResponseSchema,
    },
    url_name="remove_participant",
)
def remove_participant_endpoint(request: HttpRequest, event_slug: str, participant_identity: str):
    user: User = request.user  # type: ignore
    event: CircleEvent = get_object_or_404(CircleEvent, slug=event_slug)
    is_keeper = event.circle.author.slug == user.slug

    if not is_keeper:
        logging.warning("User %s attempted to remove participant from event %s", user.slug, event_slug)
        return 403, ErrorResponseSchema(error="Only the Keeper can remove participants.")

    if event.circle.author.slug == participant_identity:
        return 403, ErrorResponseSchema(error="Cannot remove the keeper from the room.")

    try:
        livekit.remove_participant(event.slug, participant_identity)
        return HttpResponse(status=200)
    except ParticipantNotFoundError as e:
        return 404, ErrorResponseSchema(error=str(e))
    except api.TwirpError as e:
        logging.error(f"LiveKit API error in remove_participant: {e}")
        return 500, ErrorResponseSchema(error=f"Failed to remove participant: {str(e)}")
    except Exception as e:
        logging.error(f"Unexpected error in remove_participant: {e}", exc_info=True)
        return 500, ErrorResponseSchema(error="An unexpected error occurred while removing participant.")


@meetings_router.post(
    "/event/{event_slug}/reorder",
    response={
        200: LivekitMuteParticipantSchema,
        400: ErrorResponseSchema,
        403: ErrorResponseSchema,
        404: ErrorResponseSchema,
        500: ErrorResponseSchema,
    },
    url_name="reorder_participants",
)
def reorder_participants_endpoint(request: HttpRequest, event_slug: str, order: LivekitMuteParticipantSchema):
    user: User = request.user  # type: ignore
    event: CircleEvent = get_object_or_404(CircleEvent, slug=event_slug)
    is_keeper = event.circle.author.slug == user.slug

    if not is_keeper:
        logging.warning("User %s attempted to reorder participants in event %s", user.slug, event_slug)
        return 403, ErrorResponseSchema(error="Only the Keeper can reorder participants.")

    try:
        new_order = livekit.reorder(event.slug, order.order)
        return LivekitMuteParticipantSchema(order=new_order)
    except RoomNotFoundError as e:
        return 404, ErrorResponseSchema(error=str(e))
    except RoomAlreadyEndedError as e:
        return 400, ErrorResponseSchema(error=str(e))
    except api.TwirpError as e:
        logging.error(f"LiveKit API error in reorder: {e}")
        return 500, ErrorResponseSchema(error=f"Failed to reorder participants: {str(e)}")
    except Exception as e:
        logging.error(f"Unexpected error in reorder: {e}", exc_info=True)
        return 500, ErrorResponseSchema(error="An unexpected error occurred while reordering participants.")


@meetings_router.get(
    "/event/{event_slug}/room-state",
    response={200: SessionState, 404: ErrorResponseSchema, 500: ErrorResponseSchema},
    url_name="get_room_state",
)
def get_room_state_endpoint(request: HttpRequest, event_slug: str):
    """
    Retrieves the current session state for a room.

    This endpoint exposes the SessionState schema and its enums (SessionStatus, TotemStatus)
    in the OpenAPI documentation for client-side usage.
    """
    event: CircleEvent = get_object_or_404(CircleEvent, slug=event_slug)

    try:
        state = livekit.get_room_state(event.slug)
        return state
    except RoomNotFoundError as e:
        return 404, ErrorResponseSchema(error=str(e))
    except api.TwirpError as e:
        logging.error(f"LiveKit API error in get_room_state: {e}")
        return 500, ErrorResponseSchema(error=f"Failed to retrieve room state: {str(e)}")
    except Exception as e:
        logging.error(f"Unexpected error in get_room_state: {e}", exc_info=True)
        return 500, ErrorResponseSchema(error="An unexpected error occurred while retrieving room state.")
