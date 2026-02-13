import json
import logging
from contextlib import asynccontextmanager

from asgiref.sync import async_to_sync
from django.conf import settings
from livekit import api

from totem.meetings.room_state import SessionState, SessionStatus
from totem.users.models import User

from ..spaces.models import Session

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


async def _sync_participant_names(
    room_name: str,
    lkapi: api.LiveKitAPI,
    participants: list[api.ParticipantInfo],
    slug_to_name: dict[str, str],
) -> None:
    """Syncs participant display names in LiveKit with the provided name mapping.

    Compares each participant's LiveKit display name against the provided mapping
    and updates any that are out of sync.

    Args:
        room_name: The room containing the participants.
        lkapi: An authenticated LiveKit API client instance.
        participants: The list of participants to sync.
        slug_to_name: Mapping of user slug to display name from the database.
    """
    if not participants:
        return

    for participant in participants:
        db_name = slug_to_name.get(participant.identity)
        if db_name is not None:
            expected_name = db_name or "Anonymous"
            if participant.name != expected_name:
                try:
                    await lkapi.room.update_participant(
                        api.UpdateParticipantRequest(
                            room=room_name,
                            identity=participant.identity,
                            name=expected_name,
                        )
                    )
                except api.TwirpError as e:
                    logging.error(
                        "Failed to sync name for participant %s in room %s: %s",
                        participant.identity,
                        room_name,
                        e,
                    )


@asynccontextmanager
async def _get_lk_api_client():
    """Provides an initialized and automatically closed LiveKitAPI client.

    This context manager handles LiveKit API client creation and cleanup,
    ensuring proper resource management and error handling.

    Yields:
        api.LiveKitAPI: An authenticated LiveKit API client instance.

    Raises:
        LiveKitConfigurationError: If LIVEKIT_API_KEY or LIVEKIT_API_SECRET are not configured.

    Example:
        async with _get_lk_api_client() as lkapi:
            room = await lkapi.room.list_rooms(...)
    """
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


def create_access_token(user: User, event: Session) -> str:
    """
    Create a LiveKit access token for a user to join a specific event room.

    Generates a JWT token that allows a user to participate in a live session.
    If the room doesn't exist, it will be created automatically when the user joins.
    The token is configured with appropriate permissions and room settings.

    Args:
        user: The User object attempting to join the session.
        event: The Session object representing the event/room.

    Returns:
        str: A JWT token that can be used to authenticate with LiveKit.

    Note:
        The maximum number of participants is set to the event's attendee count
        plus a buffer to accommodate late joiners.
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
    Retrieves room information from LiveKit.

    Queries the LiveKit API for a room with the specified name and returns
    the first matching room, or None if no room is found.

    Args:
        room_name: The unique identifier/name of the room to retrieve.
        lkapi: An authenticated LiveKit API client instance.

    Returns:
        api.Room | None: The room object if found, None otherwise.

    Raises:
        api.TwirpError: If the API call fails.
    """
    rooms = await lkapi.room.list_rooms(list=api.ListRoomsRequest(names=[room_name]))
    if not rooms.rooms:
        return None
    return rooms.rooms[0]


async def _get_room_or_raise(room_name: str, lkapi: api.LiveKitAPI) -> api.Room:
    """
    Retrieves room information, raising an error if not found.

    A convenience wrapper around _get_room that converts a None result
    into an exception for easier error handling.

    Args:
        room_name: The unique identifier/name of the room to retrieve.
        lkapi: An authenticated LiveKit API client instance.

    Returns:
        api.Room: The room object if found.

    Raises:
        RoomNotFoundError: If the room does not exist.
        api.TwirpError: If the API call fails.
    """
    room = await _get_room(room_name, lkapi)
    if not room:
        raise RoomNotFoundError(f"Room {room_name} does not exist.")
    return room


async def _parse_validate_room_state(
    room: api.Room,
    lkapi: api.LiveKitAPI,
    validate: bool = True,
    keeper_slug: str | None = None,
    participants: list[api.ParticipantInfo] | None = None,
    slug_to_name: dict[str, str] | None = None,
) -> SessionState:
    """
    Parses the session state from room metadata and optionally validates it.

    Deserializes the session state from room metadata JSON. If validation is enabled,
    the speaking order is verified against current participants. The keeper's presence
    can be verified if required.

    Args:
        room: The room object containing metadata to parse.
        lkapi: An authenticated LiveKit API client instance.
        validate: Whether to validate speaking order against current participants. Defaults to True.
        keeper_slug: Optional keeper slug to verify is in the room. If provided, checks that
                     the keeper is present in the participant list.
        participants: Optional pre-fetched list of participants. If not provided and needed,
                     will be fetched from the API.

    Returns:
        SessionState: A SessionState object parsed from the room metadata. If metadata is
                     missing or invalid, returns a default SessionState with empty speaking order.

    Raises:
        KeeperNotInRoomError: If keeper_slug is provided and the keeper is not in the room.
        api.TwirpError: If API calls fail when fetching participants.

    Note:
        Parse errors are logged but don't raise exceptions; instead a default state is returned.
    """
    if not room.metadata:
        return SessionState(speaking_order=[], keeper_slug="")

    try:
        metadata_dict = json.loads(room.metadata)

        participant_list = participants
        if (validate or keeper_slug) and participant_list is None:
            participants_response = await lkapi.room.list_participants(api.ListParticipantsRequest(room=room.name))
            participant_list = participants_response.participants

        if keeper_slug and participant_list is not None:
            participant_identities = [p.identity for p in participant_list]
            if keeper_slug not in participant_identities:
                raise KeeperNotInRoomError(f"Keeper {keeper_slug} is not in room {room.name}.")

        state = SessionState(**metadata_dict)

        if participant_list is not None and slug_to_name is not None:
            await _sync_participant_names(room.name, lkapi, list(participant_list), slug_to_name)

        if validate and participant_list is not None:
            participant_identities = [p.identity for p in participant_list]
            state.validate_order(participant_identities)

        return state
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        logging.error("Failed to parse room metadata for room %s: %s", room.name, e)
        return SessionState(speaking_order=[], keeper_slug="")


async def _update_room_metadata(room_name: str, state: SessionState, lkapi: api.LiveKitAPI) -> None:
    """
    Updates the room metadata with the current session state.

    Serializes the SessionState to JSON and updates the room's metadata in LiveKit.
    This persists the session state (speaking order, status, totem state, etc.)
    for retrieval by other clients.

    Args:
        room_name: The unique identifier/name of the room to update.
        state: The SessionState object to persist in room metadata.
        lkapi: An authenticated LiveKit API client instance.

    Raises:
        api.TwirpError: If the API call to update metadata fails.

    Note:
        This is a critical operation for maintaining session state across clients.
    """
    await lkapi.room.update_room_metadata(
        update=api.UpdateRoomMetadataRequest(room=room_name, metadata=json.dumps(state.dict()))
    )


@async_to_sync
async def get_room_state(room_name: str, slug_to_name: dict[str, str] | None = None) -> SessionState:
    """
    Retrieves the current session state for a room.

    Fetches the room from LiveKit and deserializes its metadata into a SessionState object.
    This provides clients with the current room status, speaking order, and totem state.

    Args:
        room_name: The unique identifier/name of the room .

    Returns:
        SessionState: The current session state for the room.

    Raises:
        RoomNotFoundError: If the room does not exist.
        api.TwirpError: If the API call fails.

    Note:
        This is a synchronous wrapper around async code using @async_to_sync.
    """
    async with _get_lk_api_client() as lkapi:
        room = await _get_room_or_raise(room_name, lkapi)
        participants_response = await lkapi.room.list_participants(api.ListParticipantsRequest(room=room_name))
        participant_list = list(participants_response.participants)
        return await _parse_validate_room_state(
            room, lkapi, validate=False, participants=participant_list, slug_to_name=slug_to_name
        )


@async_to_sync
async def initialize_room(room_name: str, speaking_order: list[str], keeper_slug: str) -> None:
    """
    Initializes a room with default metadata if it doesn't already exist.

    Creates a new LiveKit room with initial session state including the speaking order,
    keeper information, and room configuration. Only creates the room if it doesn't exist.

    Args:
        room_name: The unique identifier/name for the new room.
        speaking_order: A list of participant identities in speaking order.
        keeper_slug: The unique identifier of the keeper/session facilitator.

    Returns:
        None

    Note:
        If the room already exists, this function does nothing (idempotent).
        This is a synchronous wrapper around async code using @async_to_sync.
    """
    async with _get_lk_api_client() as lkapi:
        room = await _get_room(room_name, lkapi)
        if not room:
            state = SessionState(speaking_order=speaking_order, keeper_slug=keeper_slug)
            await lkapi.room.create_room(
                create=api.CreateRoomRequest(
                    name=room_name,
                    empty_timeout=ROOM_EMPTY_TIMEOUT_SECONDS,
                    max_participants=DEFAULT_MAX_PARTICIPANTS,
                    metadata=json.dumps(state.dict()),
                )
            )


@async_to_sync
async def pass_totem(
    room_name: str, keeper_slug: str, user_identity: str, slug_to_name: dict[str, str] | None = None
) -> None:
    """
    Passes the totem to the next participant in the speaking order.

    Transfers the current speaker role to the next person in the speaking order.
    Only the current speaker or the keeper can pass the totem. Updates the room
    metadata to reflect the new speaker.

    Args:
        room_name: The unique identifier/name of the room.
        keeper_slug: The unique identifier of the keeper/session facilitator.
        user_identity: The unique identifier of the user attempting to pass the totem.

    Returns:
        None

    Raises:
        RoomNotFoundError: If the room does not exist.
        KeeperNotInRoomError: If the keeper is not currently in the room.
        UnauthorizedError: If the user is neither the current speaker nor the keeper.
        api.TwirpError: If the API call fails.

    Note:
        The keeper can always pass the totem regardless of who is currently speaking.
        This is a synchronous wrapper around async code using @async_to_sync.
    """
    async with _get_lk_api_client() as lkapi:
        room = await _get_room_or_raise(room_name, lkapi)

        state = await _parse_validate_room_state(
            room, lkapi, validate=True, keeper_slug=keeper_slug, slug_to_name=slug_to_name
        )

        is_speaking_now = state.speaking_now == user_identity
        is_keeper = user_identity == keeper_slug
        if not is_speaking_now and not is_keeper:
            raise UnauthorizedError(
                f"User {user_identity} is not the current speaker or keeper. Cannot pass the totem."
            )

        state.pass_totem()
        await _update_room_metadata(room_name, state, lkapi)


@async_to_sync
async def accept_totem(
    room_name: str, keeper_slug: str, user_identity: str, slug_to_name: dict[str, str] | None = None
) -> None:
    """
    Accepts the totem from the current speaker in the room.

    Allows the next person in the speaking order to accept their turn to speak.
    When a totem is accepted, all other participants are automatically muted to
    ensure clear audio from the speaker. Updates the room metadata and mutes others.

    Args:
        room_name: The unique identifier/name of the room.
        keeper_slug: The unique identifier of the keeper/session facilitator.
        user_identity: The unique identifier of the user accepting the totem.

    Returns:
        None

    Raises:
        RoomNotFoundError: If the room does not exist.
        KeeperNotInRoomError: If the keeper is not currently in the room.
        NotCurrentSpeakerError: If the user is neither the next speaker nor the keeper.
        api.TwirpError: If the API call fails.

    Note:
        All other participants will be muted when the totem is accepted.
        The keeper can always accept the totem regardless of speaking order.
        This is a synchronous wrapper around async code using @async_to_sync.
    """
    async with _get_lk_api_client() as lkapi:
        room = await _get_room_or_raise(room_name, lkapi)

        participants_response = await lkapi.room.list_participants(api.ListParticipantsRequest(room=room_name))
        participant_list = list(participants_response.participants)

        state = await _parse_validate_room_state(
            room,
            lkapi,
            validate=True,
            keeper_slug=keeper_slug,
            participants=participant_list,
            slug_to_name=slug_to_name,
        )

        is_next_speaker = state.next_speaker == user_identity
        is_keeper = user_identity == keeper_slug
        if not is_next_speaker and not is_keeper:
            raise NotCurrentSpeakerError(f"User {user_identity} is not the next speaker. Cannot accept the totem.")

        state.accept_totem()
        await _update_room_metadata(room_name, state, lkapi)

        await _mute_everyone(
            room_name=room_name, lkapi=lkapi, except_identity=user_identity, participants=participant_list
        )


@async_to_sync
async def force_pass(room_name: str, keeper_slug: str, slug_to_name: dict[str, str] | None = None) -> None:
    """
    Forcefully passes the totem to the next participant, bypassing normal acceptance.

    Allows the keeper to immediately transfer the speaker role to the next person in
    the speaking order without waiting for acceptance. This can be used in cases
    where the current speaker is unresponsive or has left. Updates room metadata accordingly.

    Args:
        room_name: The unique identifier/name of the room.
        keeper_slug: The unique identifier of the keeper/session facilitator.
        user_identity: The unique identifier of the user attempting to force pass.

    Returns:
        None

    Raises:
        RoomNotFoundError: If the room does not exist.
        KeeperNotInRoomError: If the keeper is not currently in the room.
        UnauthorizedError: If the user is not the keeper.
        api.TwirpError: If the API call fails.
    """
    async with _get_lk_api_client() as lkapi:
        room = await _get_room_or_raise(room_name, lkapi)

        state = await _parse_validate_room_state(
            room, lkapi, validate=True, keeper_slug=keeper_slug, slug_to_name=slug_to_name
        )

        state.force_pass()
        await _update_room_metadata(room_name, state, lkapi)


@async_to_sync
async def start_room(room_name: str, keeper_slug: str, slug_to_name: dict[str, str] | None = None) -> None:
    """
    Starts the session in the room by updating its status to 'started'.

    Transitions the room from initialized state to started state. The speaking order
    is validated against current participants, and all participants except the first
    speaker are muted. Only the keeper can start a room.

    Args:
        room_name: The unique identifier/name of the room to start.
        keeper_slug: The unique identifier of the keeper/session facilitator.

    Returns:
        None

    Raises:
        RoomNotFoundError: If the room does not exist.
        KeeperNotInRoomError: If the keeper is not currently in the room.
        RoomAlreadyStartedError: If the room has already been started.
        api.TwirpError: If the API call fails.

    Note:
        All participants except the first speaker will be muted when the room starts.
        This is a synchronous wrapper around async code using @async_to_sync.
    """
    async with _get_lk_api_client() as lkapi:
        room = await _get_room_or_raise(room_name, lkapi)

        participants_response = await lkapi.room.list_participants(api.ListParticipantsRequest(room=room_name))
        participant_list = list(participants_response.participants)

        state = await _parse_validate_room_state(
            room,
            lkapi,
            validate=True,
            keeper_slug=keeper_slug,
            participants=participant_list,
            slug_to_name=slug_to_name,
        )

        if state.status == SessionStatus.STARTED:
            raise RoomAlreadyStartedError(f"Room {room_name} has already been started.")

        state.start()
        await _update_room_metadata(room_name, state, lkapi)
        await _mute_everyone(
            room_name=room_name,
            lkapi=lkapi,
            except_identity=state.speaking_now or keeper_slug,
            participants=participant_list,
        )


@async_to_sync
async def end_room(room_name: str) -> None:
    """
    Ends the session in the room by updating its status to 'ended'.

    Transitions the room to ended state, preventing further participant actions.
    All participants are muted when the room ends. No further operations can be
    performed on an ended room.

    Args:
        room_name: The unique identifier/name of the room to end.

    Returns:
        None

    Raises:
        RoomNotFoundError: If the room does not exist.
        RoomAlreadyEndedError: If the room has already been ended.
        api.TwirpError: If the API call fails.

    Note:
        All participants will be muted when the room ends.
        Once ended, a room cannot be restarted.
        This is a synchronous wrapper around async code using @async_to_sync.
    """
    async with _get_lk_api_client() as lkapi:
        room = await _get_room_or_raise(room_name, lkapi)

        state = await _parse_validate_room_state(room, lkapi, validate=False)

        if state.status == SessionStatus.ENDED:
            raise RoomAlreadyEndedError(f"Room {room_name} has already ended.")

        state.end()
        await _update_room_metadata(room_name, state, lkapi)
        await _mute_everyone(room_name=room_name, lkapi=lkapi)


@async_to_sync
async def reorder(room_name: str, new_order: list[str], slug_to_name: dict[str, str] | None = None) -> list[str]:
    """
    Reorders the participants in the room's speaking order.

    Updates the speaking order while ensuring only participants currently connected
    to the room are included. Participants in the new_order list who are not
    currently connected are silently filtered out. Updates room metadata with
    the new order.

    Args:
        room_name: The unique identifier/name of the room.
        new_order: A list of participant identities in the desired speaking order.

    Returns:
        list[str]: The updated speaking order containing only connected participants.

    Raises:
        RoomNotFoundError: If the room does not exist.
        RoomAlreadyEndedError: If the room has already been ended.
        api.TwirpError: If the API call fails.

    Note:
        Disconnected participants in new_order are filtered out without raising errors.
        The actual returned order may be shorter than new_order if some participants
        are not connected.
        This is a synchronous wrapper around async code using @async_to_sync.
    """
    async with _get_lk_api_client() as lkapi:
        room = await _get_room_or_raise(room_name, lkapi)

        participants_response = await lkapi.room.list_participants(api.ListParticipantsRequest(room=room_name))
        participant_list = list(participants_response.participants)
        participant_identities = [p.identity for p in participant_list]

        state = await _parse_validate_room_state(room, lkapi, participants=participant_list, slug_to_name=slug_to_name)

        if state.status == SessionStatus.ENDED:
            raise RoomAlreadyEndedError(f"Room {room_name} has already ended.")

        filtered_order = [identity for identity in new_order if identity in participant_identities]

        state.reorder(filtered_order)
        state = await _parse_validate_room_state(
            room, lkapi, validate=True, participants=participant_list, slug_to_name=slug_to_name
        )
        await _update_room_metadata(room_name, state, lkapi)

        return state.speaking_order


@async_to_sync
async def mute_participant(room_name: str, user_identity: str) -> None:
    """
    Mutes audio for a specific participant in the room.

    Finds the participant's audio track and mutes it. This prevents the participant
    from being heard by others, though they can still hear the session.

    Args:
        room_name: The unique identifier/name of the room.
        user_identity: The unique identifier of the participant to mute.

    Returns:
        None

    Raises:
        ParticipantNotFoundError: If the participant is not found in the room.
        NoAudioTrackError: If the participant has no audio track to mute.
        api.TwirpError: If the API call fails.

    Note:
        This operation is one-way; use the LiveKit API directly to unmute.
        This is a synchronous wrapper around async code using @async_to_sync.
    """
    async with _get_lk_api_client() as lkapi:
        participant = await lkapi.room.get_participant(
            api.RoomParticipantIdentity(room=room_name, identity=user_identity)
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


@async_to_sync
async def mute_all_participants(room_name: str, except_identity: str | None = None) -> None:
    """
    Mutes audio for all participants in the room.

    Mutes all participants' audio tracks, optionally excluding one participant.
    Useful for ensuring silence when transitioning between speakers or ending sessions.

    Args:
        room_name: The unique identifier/name of the room.
        except_identity: Optional participant identity to exclude from muting.
                        If None, all participants are muted. Defaults to None.

    Returns:
        None

    Note:
        This is a synchronous wrapper around async code using @async_to_sync.
        Muting errors for individual participants are logged but don't stop the operation.
    """
    async with _get_lk_api_client() as lkapi:
        await _mute_everyone(room_name=room_name, lkapi=lkapi, except_identity=except_identity)


async def _mute_everyone(
    room_name: str,
    lkapi: api.LiveKitAPI,
    except_identity: str | None = None,
    participants: list[api.ParticipantInfo] | None = None,
):
    """
    Mutes all audio in a room, optionally excluding one participant.

    Internal helper function that mutes all participants' audio tracks in a room.
    Accepts pre-fetched participants to avoid redundant API calls. Errors during
    individual participant muting are logged but don't interrupt the operation.

    Args:
        room_name: The unique identifier/name of the room.
        lkapi: An authenticated LiveKit API client instance.
        except_identity: Optional participant identity to exclude from muting.
                        If provided, this participant will not be muted. Defaults to None.
        participants: Optional pre-fetched list of participants. If not provided,
                     will be fetched from the API. Defaults to None.

    Returns:
        None

    Raises:
        api.TwirpError: If fetching participants fails (only if participants not provided).

    Note:
        Errors while muting individual participants are logged but don't raise exceptions.
        This allows the operation to continue for other participants even if some fail.
    """
    participant_list = participants
    if participant_list is None:
        participants_response = await lkapi.room.list_participants(api.ListParticipantsRequest(room=room_name))
        participant_list = list(participants_response.participants)

    for participant in participant_list:
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
                    logging.error(
                        "Failed to mute participant %s in room %s: %s",
                        participant.identity,
                        room_name,
                        e,
                    )
                    continue


@async_to_sync
async def remove_participant(room_name: str, user_identity: str) -> None:
    """
    Removes a participant from the room, disconnecting them.

    Forcibly disconnects a participant from the room. Once removed, the participant
    must obtain a new access token to rejoin the session.

    Args:
        room_name: The unique identifier/name of the room.
        user_identity: The unique identifier of the participant to remove.

    Returns:
        None

    Raises:
        ParticipantNotFoundError: If the participant is not found in the room or if
                                the removal API call fails.
        api.TwirpError: If the API call fails.

    Note:
        This is a permanent removal; the participant cannot continue in the session
        without explicitly rejoining.
        This is a synchronous wrapper around async code using @async_to_sync.
    """
    async with _get_lk_api_client() as lkapi:
        try:
            participant = await lkapi.room.remove_participant(
                api.RoomParticipantIdentity(room=room_name, identity=user_identity)
            )
        except api.TwirpError as e:
            raise ParticipantNotFoundError(
                f"Failed to remove participant {user_identity} from room {room_name}: {e}"
            ) from e

        if not participant:
            raise ParticipantNotFoundError(f"Participant {user_identity} not found in room {room_name}.")


@async_to_sync
async def is_user_in_room(room_name: str, user_identity: str) -> bool:
    """
    Check if a user is currently in a LiveKit room.

    Args:
        room_name: The unique identifier/name of the room (typically session slug).
        user_identity: The unique identifier of the user (typically user slug).

    Returns:
        bool: True if the user is in the room, False otherwise.

    Note:
        Returns False if the room doesn't exist or LiveKit is not configured.
        This is a synchronous wrapper around async code using @async_to_sync.
    """
    try:
        async with _get_lk_api_client() as lkapi:
            room = await _get_room(room_name, lkapi)
            if room is None:
                return False
            participants_response = await lkapi.room.list_participants(api.ListParticipantsRequest(room=room_name))
            return any(p.identity == user_identity for p in participants_response.participants)
    except LiveKitConfigurationError:
        return False
    except api.TwirpError:
        return False
