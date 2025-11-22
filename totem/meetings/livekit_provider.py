import json
import logging
from contextlib import asynccontextmanager

from asgiref.sync import async_to_sync
from django.conf import settings
from livekit import api

from totem.meetings.room_state import SessionState, SessionStatus
from totem.users.models import User

from ..circles.models import CircleEvent

# Constants
ROOM_EMPTY_TIMEOUT_SECONDS = 60 * 60  # 1 hour
DEFAULT_MAX_PARTICIPANTS = 20
EXTRA_PARTICIPANT_BUFFER = 5


class LiveKitException(Exception):
    """Base exception for LiveKit-related errors."""

    pass


class LiveKitConfigurationError(LiveKitException):
    """Raised when LiveKit is not properly configured."""

    pass


class RoomNotFoundError(LiveKitException):
    """Raised when a room does not exist."""

    pass


class ParticipantNotFoundError(LiveKitException):
    """Raised when a participant is not found in a room."""

    pass


class KeeperNotInRoomError(LiveKitException):
    """Raised when the keeper is not in the room."""

    pass


class UnauthorizedError(LiveKitException):
    """Raised when a user is not authorized to perform an action."""

    pass


class NotCurrentSpeakerError(LiveKitException):
    """Raised when a user is not the current speaker."""

    pass


class RoomAlreadyStartedError(LiveKitException):
    """Raised when attempting to start a room that has already been started."""

    pass


class RoomAlreadyEndedError(LiveKitException):
    """Raised when attempting to perform an action on a room that has already ended."""

    pass


class NoAudioTrackError(LiveKitException):
    """Raised when a participant has no audio track."""

    pass


@asynccontextmanager
async def _get_lk_api_client():
    """Provides an initialized and automatically closed LiveKitAPI client."""
    if not settings.LIVEKIT_API_KEY or not settings.LIVEKIT_API_SECRET:
        raise LiveKitConfigurationError("LiveKit API key and secret are not configured.")

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
                empty_timeout=ROOM_EMPTY_TIMEOUT_SECONDS,
                max_participants=attendees_count + EXTRA_PARTICIPANT_BUFFER,
            )
        )
    )

    return token.to_jwt()


async def _get_room(room_name: str, lkapi: api.LiveKitAPI) -> api.Room | None:
    """
    Retrieves room information.

    Args:
        room_name: The name of the room to retrieve.
        lkapi: The LiveKit API client.

    Returns:
        The room object if found, None otherwise.
    """
    rooms = await lkapi.room.list_rooms(
        list=api.ListRoomsRequest(
            names=[room_name],
        )
    )
    if not rooms.rooms:
        return None
    return rooms.rooms[0]


async def _get_room_or_raise(room_name: str, lkapi: api.LiveKitAPI) -> api.Room:
    """
    Retrieves room information or raises an error if not found.

    Args:
        room_name: The name of the room to retrieve.
        lkapi: The LiveKit API client.

    Returns:
        The room object.

    Raises:
        RoomNotFoundError: If the room does not exist.
    """
    room = await _get_room(room_name, lkapi)
    if not room:
        raise RoomNotFoundError(f"Room {room_name} does not exist.")
    return room


@async_to_sync
async def get_room_state(room_name: str) -> SessionState:
    """
    Retrieves the current session state for a room.

    Args:
        room_name: The name of the room.

    Returns:
        The current SessionState for the room.

    Raises:
        RoomNotFoundError: If the room does not exist.
    """
    async with _get_lk_api_client() as lkapi:
        room = await _get_room_or_raise(room_name, lkapi)
        return await _parse_room_state(room)


async def _parse_room_state(room: api.Room) -> SessionState:
    """
    Parses the session state from room metadata.

    Args:
        room: The room object containing metadata.

    Returns:
        A SessionState object parsed from the room metadata.

    Raises:
        ValueError: If the metadata contains invalid JSON.
    """
    if not room.metadata:
        return SessionState(speaking_order=[])

    try:
        current_state = json.loads(room.metadata)
        return SessionState(**current_state)
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        logging.error("Failed to parse room metadata for room %s: %s", room.name, e)
        # Return a default state if parsing fails
        return SessionState(speaking_order=[])


async def _update_room_metadata(room_name: str, state: SessionState, lkapi: api.LiveKitAPI) -> None:
    """
    Updates the room metadata with the current session state.

    Args:
        room_name: The name of the room to update.
        state: The session state to save.
        lkapi: The LiveKit API client.

    Raises:
        api.TwirpError: If the API call fails.
    """
    await lkapi.room.update_room_metadata(
        update=api.UpdateRoomMetadataRequest(
            room=room_name,
            metadata=json.dumps(state.dict()),
        )
    )


async def _ensure_keeper_in_room(room_name: str, keeper_slug: str, lkapi: api.LiveKitAPI) -> None:
    """
    Ensures that the keeper is in the room.

    Args:
        room_name: The name of the room.
        keeper_slug: The slug of the keeper to verify.
        lkapi: The LiveKit API client.

    Raises:
        KeeperNotInRoomError: If the keeper is not in the room.
    """
    participant = await lkapi.room.get_participant(
        api.RoomParticipantIdentity(
            room=room_name,
            identity=keeper_slug,
        )
    )
    if not participant:
        raise KeeperNotInRoomError(f"Keeper {keeper_slug} is not in room {room_name}.")


@async_to_sync
async def initialize_room(room_name: str, speaking_order: list[str]) -> None:
    """
    Initializes a room with default metadata if it doesn't exist.

    Args:
        room_name: The name of the room to initialize.
        speaking_order: The initial speaking order for the room.
    """
    async with _get_lk_api_client() as lkapi:
        room = await _get_room(room_name, lkapi)
        if not room:
            state = SessionState(speaking_order=speaking_order)
            await lkapi.room.create_room(
                create=api.CreateRoomRequest(
                    name=room_name,
                    empty_timeout=ROOM_EMPTY_TIMEOUT_SECONDS,
                    max_participants=DEFAULT_MAX_PARTICIPANTS,
                    metadata=json.dumps(state.dict()),
                )
            )


@async_to_sync
async def pass_totem(room_name: str, keeper_slug: str, user_identity: str) -> None:
    """
    Passes the totem to the next participant in the room.

    Args:
        room_name: The name of the room.
        keeper_slug: The slug of the keeper (who can always pass the totem).
        user_identity: The identity of the user attempting to pass the totem.

    Raises:
        RoomNotFoundError: If the room doesn't exist.
        KeeperNotInRoomError: If the keeper is not in room.
        UnauthorizedError: If user is not authorized to pass the totem.
    """
    async with _get_lk_api_client() as lkapi:
        room = await _get_room_or_raise(room_name, lkapi)
        await _ensure_keeper_in_room(room_name, keeper_slug, lkapi)

        state = await _parse_room_state(room)

        is_speaking_now = state.speaking_now == user_identity
        is_keeper = user_identity == keeper_slug
        if not is_speaking_now and not is_keeper:
            raise UnauthorizedError(
                f"User {user_identity} is not the current speaker or keeper. Cannot pass the totem."
            )

        state.pass_totem()
        await _update_room_metadata(room_name, state, lkapi)


@async_to_sync
async def accept_totem(room_name: str, keeper_slug: str, user_identity: str) -> None:
    """
    Accepts the totem from the current speaker in the room.

    When accepting the totem, all other participants are muted.

    Args:
        room_name: The name of the room.
        keeper_slug: The slug of the keeper.
        user_identity: The identity of the user accepting the totem.

    Raises:
        RoomNotFoundError: If the room doesn't exist.
        KeeperNotInRoomError: If the keeper is not in room.
        NotCurrentSpeakerError: If user is not the current speaker.
    """
    async with _get_lk_api_client() as lkapi:
        room = await _get_room_or_raise(room_name, lkapi)
        await _ensure_keeper_in_room(room_name, keeper_slug, lkapi)

        state = await _parse_room_state(room)

        if state.speaking_now != user_identity:
            raise NotCurrentSpeakerError(f"User {user_identity} is not the current speaker. Cannot accept the totem.")

        state.accept_totem()
        await _update_room_metadata(room_name, state, lkapi)

        # Mute all other participants except the one accepting the totem
        await _mute_everyone(room_name=room_name, lkapi=lkapi, except_identity=user_identity)


@async_to_sync
async def start_room(room_name: str, keeper_slug: str) -> None:
    """
    Starts the session in the room by updating its status to 'started'.

    The speaking order is validated against current participants before starting.

    Args:
        room_name: The name of the room to start.
        keeper_slug: The slug of the keeper.

    Raises:
        RoomNotFoundError: If the room doesn't exist.
        KeeperNotInRoomError: If the keeper is not in room.
        RoomAlreadyStartedError: If the room has already been started.
    """
    async with _get_lk_api_client() as lkapi:
        room = await _get_room_or_raise(room_name, lkapi)
        await _ensure_keeper_in_room(room_name, keeper_slug, lkapi)

        state = await _parse_room_state(room)

        if state.status == SessionStatus.STARTED:
            raise RoomAlreadyStartedError(f"Room {room_name} has already been started.")

        participants = await lkapi.room.list_participants(
            api.ListParticipantsRequest(
                room=room_name,
            )
        )
        state.validate_order([participant.identity for participant in participants.participants])
        state.start()
        await _update_room_metadata(room_name, state, lkapi)


@async_to_sync
async def end_room(room_name: str) -> None:
    """
    Ends the session in the room by updating its status to 'ended'.

    All participants are muted when the room ends.

    Args:
        room_name: The name of the room to end.

    Raises:
        RoomNotFoundError: If the room doesn't exist.
        RoomAlreadyEndedError: If the room has already ended.
    """
    async with _get_lk_api_client() as lkapi:
        room = await _get_room_or_raise(room_name, lkapi)

        state = await _parse_room_state(room)

        if state.status == SessionStatus.ENDED:
            raise RoomAlreadyEndedError(f"Room {room_name} has already ended.")

        state.end()
        await _update_room_metadata(room_name, state, lkapi)
        await _mute_everyone(room_name=room_name, lkapi=lkapi)


@async_to_sync
async def reorder(room_name: str, new_order: list[str]) -> list[str]:
    """
    Reorders the participants in the room.

    Args:
        room_name: The name of the room.
        new_order: The new speaking order.

    Returns:
        The updated speaking order.

    Raises:
        RoomNotFoundError: If the room doesn't exist.
        RoomAlreadyEndedError: If the room has already ended.
    """
    async with _get_lk_api_client() as lkapi:
        room = await _get_room_or_raise(room_name, lkapi)

        state = await _parse_room_state(room)

        if state.status == SessionStatus.ENDED:
            raise RoomAlreadyEndedError(f"Room {room_name} has already ended.")

        state.reorder(new_order)
        await _update_room_metadata(room_name, state, lkapi)

        return state.speaking_order


@async_to_sync
async def mute_participant(room_name: str, user_identity: str) -> None:
    """
    Mutes a participant in the room.

    Args:
        room_name: The name of the room.
        user_identity: The identity of the participant to mute.

    Raises:
        ParticipantNotFoundError: If the participant is not found.
        NoAudioTrackError: If the participant has no audio track.
        api.TwirpError: If the API call fails.
    """
    async with _get_lk_api_client() as lkapi:
        participant = await lkapi.room.get_participant(
            api.RoomParticipantIdentity(
                room=room_name,
                identity=user_identity,
            )
        )

        if not participant:
            raise ParticipantNotFoundError(f"Participant {user_identity} not found in room {room_name}.")

        track_sid = None
        for track in participant.tracks:
            if track.type == api.TrackType.AUDIO:
                track_sid = track.sid
                break

        if track_sid is None:
            raise NoAudioTrackError(f"Participant {user_identity} has no audio track to mute in room {room_name}.")

        await lkapi.room.mute_published_track(
            api.MuteRoomTrackRequest(
                room=room_name,
                identity=participant.identity,
                track_sid=track_sid,
                muted=True,
            )
        )


async def _mute_everyone(room_name: str, lkapi: api.LiveKitAPI, except_identity: str | None = None):
    """
    Mutes everyone in the room.

    If except_identity is provided, the participant with that identity is not muted.

    If the participant is not found, it is not muted.
    """
    participants = await lkapi.room.list_participants(
        api.ListParticipantsRequest(
            room=room_name,
        )
    )
    for participant in participants.participants:
        if except_identity and participant.identity == except_identity:
            continue
        for track in participant.tracks:
            if track.type == api.TrackType.AUDIO:
                try:
                    await lkapi.room.mute_published_track(
                        api.MuteRoomTrackRequest(
                            room=room_name,
                            identity=participant.identity,
                            track_sid=track.sid,
                            muted=True,
                        )
                    )
                except api.TwirpError as e:
                    logging.error("Failed to mute participant %s in room %s: %s", participant.identity, room_name, e)
                    continue


@async_to_sync
async def remove_participant(room_name: str, user_identity: str) -> None:
    """
    Removes a participant from the room.

    Args:
        room_name: The name of the room.
        user_identity: The identity of the participant to remove.

    Raises:
        ParticipantNotFoundError: If the participant removal fails or participant is not found.
        api.TwirpError: If the API call fails.
    """
    async with _get_lk_api_client() as lkapi:
        try:
            participant = await lkapi.room.remove_participant(
                api.RoomParticipantIdentity(
                    room=room_name,
                    identity=user_identity,
                )
            )
        except api.TwirpError as e:
            raise ParticipantNotFoundError(
                f"Failed to remove participant {user_identity} from room {room_name}: {e}"
            ) from e

        if not participant:
            raise ParticipantNotFoundError(f"Participant {user_identity} not found in room {room_name}.")
