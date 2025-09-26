from asgiref.sync import async_to_sync
from django.conf import settings
from livekit.api import AccessToken, CreateRoomRequest, ListRoomsRequest, LiveKitAPI, Room, VideoGrants

from totem.users.models import User

from ..circles.models import CircleEvent


async def _get_or_create_room_async(user: User, event: CircleEvent) -> Room:
    """
    Retrieves or creates a LiveKit room for the given event.
    """
    if not settings.LIVEKIT_API_KEY or not settings.LIVEKIT_API_SECRET:
        raise ValueError("LiveKit API key and secret are not configured.")

    lkapi = LiveKitAPI()
    room_name = event.slug

    # If room exists, return it
    response = await lkapi.room.list_rooms(list=ListRoomsRequest(names=[room_name]))
    if response.rooms:
        return response.rooms[0]

    # If room doesn't exist, create it (only staff can create rooms)
    if user.is_staff:
        new_room = await lkapi.room.create_room(
            create=CreateRoomRequest(
                name=room_name,
                empty_timeout=60 * 60,  # 1 hour
                max_participants=event.attendees.count() + 5,  # attendees + some buffer
            )
        )
        return new_room

    raise ValueError("Room does not exist and user is not authorized to create it.")


@async_to_sync
async def get_or_create_room(user: User, event: CircleEvent) -> Room:
    """
    Retrieves or creates a LiveKit room for the given event.
    This is a synchronous wrapper around the async implementation.
    """
    if not settings.LIVEKIT_API_KEY or not settings.LIVEKIT_API_SECRET:
        raise ValueError("LiveKit API key and secret are not configured.")
    return await _get_or_create_room_async(user=user, event=event)


def livekit_create_access_token(user: User, event: CircleEvent) -> str:
    """
    Generates a LiveKit access token for a user to join a specific event room.
    """
    if not settings.LIVEKIT_API_KEY or not settings.LIVEKIT_API_SECRET:
        raise ValueError("LiveKit API key and secret are not configured.")

    participant_identity = user.slug

    room = get_or_create_room(user, event)

    token = (
        AccessToken(settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET)
        .with_identity(participant_identity)
        .with_name(user.name or "Anonymous")
        .with_grants(
            VideoGrants(
                room=room.name,
                can_subscribe=True,
                room_join=True,
            )
        )
    )

    return token.to_jwt()
