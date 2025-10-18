import json

from asgiref.sync import sync_to_async
from django.conf import settings
from livekit import api

from totem.meetings.room_state import SessionState
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


async def get_room(room_name: str) -> api.Room | None:
    """
    Retrieves room information.
    """
    if not settings.LIVEKIT_API_KEY or not settings.LIVEKIT_API_SECRET:
        return None

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
            return None
        return rooms.rooms[0]
    finally:
        await lkapi.aclose()


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


async def initialize_room(room_name: str, speaking_order: list[str]):
    """
    Initializes a room with default metadata if it doesn't exist.
    """
    if not settings.LIVEKIT_API_KEY or not settings.LIVEKIT_API_SECRET:
        return

    lkapi = api.LiveKitAPI(
        # url=settings.LIVEKIT_URL,
        api_key=settings.LIVEKIT_API_KEY,
        api_secret=settings.LIVEKIT_API_SECRET,
    )
    try:
        room = await get_room(room_name)
        if not room:
            state = SessionState(speaking_order=speaking_order)
            await lkapi.room.create_room(
                create=api.CreateRoomRequest(
                    name=room_name,
                    empty_timeout=60 * 60,  # 1 hour
                    max_participants=20,
                    metadata=json.dumps(state.dict()),
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
        room = await get_room(room_name)
        if not room:
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


async def propagate_pass_totem(room_name: str, user_identity: str):
    """
    Passes the totem to the next participant in the room.
    """

    if not settings.LIVEKIT_API_KEY or not settings.LIVEKIT_API_SECRET:
        return

    lkapi = api.LiveKitAPI(
        # url=settings.LIVEKIT_URL,
        api_key=settings.LIVEKIT_API_KEY,
        api_secret=settings.LIVEKIT_API_SECRET,
    )

    try:
        room = await get_room(room_name)
        if not room:
            raise ValueError(f"Room {room_name} does not exist.")

        current_state = json.loads(room.metadata) if room.metadata else {}
        state = SessionState(**current_state)

        if state.speaking_now != user_identity:
            raise ValueError(f"User {user_identity} is not the current speaker. Cannot pass the totem.")

        state.pass_totem()
        await lkapi.room.update_room_metadata(
            update=api.UpdateRoomMetadataRequest(
                room=room_name,
                metadata=json.dumps(state.dict()),
            )
        )
    finally:
        await lkapi.aclose()
