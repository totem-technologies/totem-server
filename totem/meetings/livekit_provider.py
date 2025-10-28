import json
from contextlib import asynccontextmanager
from typing import List

from asgiref.sync import async_to_sync
from django.conf import settings
from livekit import api

from totem.meetings.room_state import SessionState, SessionStatus
from totem.users.models import User

from ..circles.models import CircleEvent


@asynccontextmanager
async def get_lk_api_client():
    """Provides an initialized and automatically closed LiveKitAPI client."""
    if not settings.LIVEKIT_API_KEY or not settings.LIVEKIT_API_SECRET:
        raise ValueError("LiveKit API key and secret are not configured.")

    lkapi = api.LiveKitAPI(
        # url=settings.LIVEKIT_URL,
        api_key=settings.LIVEKIT_API_KEY,
        api_secret=settings.LIVEKIT_API_SECRET,
    )
    try:
        yield lkapi
    finally:
        await lkapi.aclose()


def create_access_token(user: User, event: CircleEvent) -> str:
    """
    Create a LiveKit access token for a user to join a specific event room.

    If the room doesn't exist, it will be created automatically when the user joins.
    """

    participant_identity = user.slug
    room_name = event.slug
    attendees_count = event.attendees.count()

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


async def get_room(room_name: str, lkapi: api.LiveKitAPI) -> api.Room | None:
    """
    Retrieves room information.
    """
    rooms = await lkapi.room.list_rooms(
        list=api.ListRoomsRequest(
            names=[room_name],
        )
    )
    if not rooms.rooms:
        return None
    return rooms.rooms[0]


@async_to_sync
async def initialize_room(room_name: str, speaking_order: list[str]):
    """
    Initializes a room with default metadata if it doesn't exist.
    """
    async with get_lk_api_client() as lkapi:
        room = await get_room(room_name, lkapi)
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


@async_to_sync
async def pass_totem(room_name: str, user_identity: str):
    """
    Passes the totem to the next participant in the room.
    """

    async with get_lk_api_client() as lkapi:
        room = await get_room(room_name, lkapi)
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


@async_to_sync
async def accept_totem(room_name: str, user_identity: str):
    """
    Accepts the totem from the current speaker in the room.
    """

    async with get_lk_api_client() as lkapi:
        room = await get_room(room_name, lkapi)
        if not room:
            raise ValueError(f"Room {room_name} does not exist.")

        current_state = json.loads(room.metadata) if room.metadata else {}
        state = SessionState(**current_state)

        # The current speaker should already be the current user. If not, it's not their turn to speak.
        # When accepting the totem, we mute all other participants.
        if state.speaking_now != user_identity:
            raise ValueError(f"User {user_identity} is not the current speaker. Cannot accept the totem.")

        # Mute all other participants except the one accepting the totem
        for participant in state.speaking_order:
            if participant != user_identity:
                await lkapi.room.mute_published_track(
                    api.MuteRoomTrackRequest(
                        room=room_name,
                        identity=participant,
                        track_sid="",  # Empty track_sid to mute all audio tracks
                        muted=True,
                    )
                )


@async_to_sync
async def start_room(room_name: str):
    """
    Starts the session in the room by updating its status to 'started'.
    """

    async with get_lk_api_client() as lkapi:
        room = await get_room(room_name, lkapi)  # Pass the client in
        if not room:
            raise ValueError(f"Room {room_name} does not exist.")

        current_state = json.loads(room.metadata) if room.metadata else {}
        state = SessionState(**current_state)

        if state.status == SessionStatus.STARTED:
            raise ValueError(f"Room {room_name} has already been started.")

        state.start()
        await lkapi.room.update_room_metadata(
            update=api.UpdateRoomMetadataRequest(
                room=room_name,
                metadata=json.dumps(state.dict()),
            )
        )


@async_to_sync
async def reorder(room_name: str, new_order: List[str]) -> List[str]:
    """
    Reorders the participants in the room.
    """

    async with get_lk_api_client() as lkapi:
        room = await get_room(room_name, lkapi)
        if not room:
            raise ValueError(f"Room {room_name} does not exist.")

        current_state = json.loads(room.metadata) if room.metadata else {}
        state = SessionState(**current_state)

        if state.status == SessionStatus.ENDED:
            raise ValueError(f"Room {room_name} has already ended.")

        state.reorder(new_order)
        await lkapi.room.update_room_metadata(
            update=api.UpdateRoomMetadataRequest(
                room=room_name,
                metadata=json.dumps(state.dict()),
            )
        )
        
        return state.speaking_order


@async_to_sync
async def mute_participant(room_name: str, user_identity: str):
    """
    Mutes a participant in the room.
    """

    async with get_lk_api_client() as lkapi:
        room = await get_room(room_name, lkapi)
        if not room:
            raise ValueError(f"Room {room_name} does not exist.")

        participant = await lkapi.room.get_participant(
            api.RoomParticipantIdentity(
                room=room_name,
                identity=user_identity,
            )
        )

        if not participant:
            raise ValueError(f"Participant {user_identity} not found in room {room_name}.")

        track_sid = None
        for track in participant.tracks:
            if track.type == api.TrackType.AUDIO:
                track_sid = track.sid
                break

        await lkapi.room.mute_published_track(
            api.MuteRoomTrackRequest(
                room=room_name,
                identity=participant.identity,
                track_sid=track_sid,
                muted=True,
            )
        )


@async_to_sync
async def remove_participant(room_name: str, user_identity: str):
    """
    Removes a participant from the room.
    """

    async with get_lk_api_client() as lkapi:
        room = await get_room(room_name, lkapi)
        if not room:
            raise ValueError(f"Room {room_name} does not exist.")

        participant = await lkapi.room.remove_participant(
            api.RoomParticipantIdentity(
                room=room_name,
                identity=user_identity,
            )
        )

        if not participant:
            raise ValueError(f"Participant {user_identity} not found in room {room_name}.")
