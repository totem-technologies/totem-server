import json

from asgiref.sync import sync_to_async
from django.conf import settings
from livekit import api

from totem.users.models import User

from ..circles.models import CircleEvent


async def livekit_create_access_token(user: User, event: CircleEvent) -> str:
    """
    Create a LiveKit access token for a user to join a specific event room.

    If the room doesn't exist, it will be created automatically when the user joins.
    """
    if not settings.LIVEKIT_API_KEY or not settings.LIVEKIT_API_SECRET:
        raise ValueError("LiveKit API key and secret are not configured.")

    participant_identity = user.slug
    room_name = event.slug
    attendees_count = await sync_to_async(event.attendees.count)()

    token = (
        api.AccessToken(settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET)
        .with_identity(participant_identity)
        .with_name(user.name or "Anonymous")
        .with_grants(
            api.VideoGrants(
                room=room_name,
                can_subscribe=True,
                room_join=True,
            )
        )
        .with_room_config(
            config=api.RoomConfiguration(
                name=room_name,
                empty_timeout=60 * 60,  # 1 hour
                max_participants=attendees_count + 5,
            )
        )
    )

    return token.to_jwt()


async def send_data(room_name: str, data: dict):
    """
    Sends data to all participants in a room.
    """
    if not settings.LIVEKIT_API_KEY or not settings.LIVEKIT_API_SECRET:
        return

    lkapi = api.LiveKitAPI(
        url=settings.LIVEKIT_URL, api_key=settings.LIVEKIT_API_KEY, api_secret=settings.LIVEKIT_API_SECRET
    )
    try:
        payload = json.dumps(data).encode("utf-8")
        await lkapi.room.send_data(
            send=api.SendDataRequest(
                room=room_name,
                data=payload,
                kind=api.DataPacket.Kind.RELIABLE,
                topic="lk-session-state-topic",
            )
        )
    finally:
        await lkapi.aclose()


async def update_room_metadata(room_name: str, metadata: dict):
    """
    Updates the metadata of a room.
    """
    if not settings.LIVEKIT_API_KEY or not settings.LIVEKIT_API_SECRET:
        return

    lkapi = api.LiveKitAPI(
        # url=settings.LIVEKIT_URL,
        api_key=settings.LIVEKIT_API_KEY,
        api_secret=settings.LIVEKIT_API_SECRET,
    )
    try:
        rooms = await lkapi.room.list_rooms(
            list=api.ListRoomsRequest(
                names=[room_name],
            )
        )
        if not rooms.rooms:
            await lkapi.room.create_room(
                create=api.CreateRoomRequest(
                    name=room_name,
                    empty_timeout=60 * 60,  # 1 hour
                    max_participants=20,
                    metadata=json.dumps(metadata),
                )
            )
        else:
            await lkapi.room.update_room_metadata(
                update=api.UpdateRoomMetadataRequest(
                    room=room_name,
                    metadata=json.dumps(metadata),
                )
            )
    finally:
        await lkapi.aclose()
