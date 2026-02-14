"""
LiveKit integration helpers.

All LiveKit API calls live here — nowhere else in the app talks to LiveKit.
"""

from __future__ import annotations

import json
import logging

from asgiref.sync import async_to_sync
from django.conf import settings
from livekit import api

from totem.users.models import User

from .schemas import RoomState

logger = logging.getLogger(__name__)


async def _get_connected_participants(room_name: str) -> set[str]:
    if not settings.LIVEKIT_API_KEY or not settings.LIVEKIT_API_SECRET:
        return set()

    lkapi = api.LiveKitAPI(
        api_key=settings.LIVEKIT_API_KEY,
        api_secret=settings.LIVEKIT_API_SECRET,
    )
    try:
        resp = await lkapi.room.list_participants(api.ListParticipantsRequest(room=room_name))
        return {p.identity for p in resp.participants}
    except Exception:
        logger.exception("Failed to list participants for room %s", room_name)
        return set()
    finally:
        await lkapi.aclose()


async def _publish_state(room_name: str, state: RoomState) -> None:
    if not settings.LIVEKIT_API_KEY or not settings.LIVEKIT_API_SECRET:
        return

    lkapi = api.LiveKitAPI(
        api_key=settings.LIVEKIT_API_KEY,
        api_secret=settings.LIVEKIT_API_SECRET,
    )
    try:
        await lkapi.room.update_room_metadata(
            update=api.UpdateRoomMetadataRequest(
                room=room_name,
                metadata=json.dumps(state.dict()),
            )
        )
    except Exception:
        logger.exception("Failed to publish state for room %s", room_name)
    finally:
        await lkapi.aclose()


@async_to_sync
async def get_connected_participants(room_name: str) -> set[str]:
    """
    Returns the set of user slugs currently connected to the LiveKit room.
    Gracefully returns an empty set on errors or missing config.
    """
    return await _get_connected_participants(room_name)


@async_to_sync
async def publish_state(room_name: str, state: RoomState) -> None:
    """
    Publishes the state snapshot to LiveKit room metadata.
    Fire-and-forget — failures are logged but don't raise.
    """
    await _publish_state(room_name, state)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ROOM_EMPTY_TIMEOUT_SECONDS = 60 * 60  # 1 hour
EXTRA_PARTICIPANT_BUFFER = 5


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class LiveKitConfigurationError(Exception):
    """Raised when LiveKit API key/secret are not configured."""


class ParticipantNotFoundError(Exception):
    """Raised when a participant is not found in a room."""


class NoAudioTrackError(Exception):
    """Raised when a participant has no audio track to mute."""


# ---------------------------------------------------------------------------
# Token generation
# ---------------------------------------------------------------------------


def create_access_token(user: User, session) -> str:
    """
    Create a LiveKit access token for a user to join a session room.
    Raises LiveKitConfigurationError if LiveKit is not configured.
    """
    if not settings.LIVEKIT_API_KEY or not settings.LIVEKIT_API_SECRET:
        raise LiveKitConfigurationError("LiveKit API key and secret are not configured.")

    attendees_count = session.attendees.count()
    room_name = session.slug

    token = (
        api.AccessToken(settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET)
        .with_identity(user.slug)
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


# ---------------------------------------------------------------------------
# Participant management
# ---------------------------------------------------------------------------


async def _mute_participant(room_name: str, identity: str) -> None:
    if not settings.LIVEKIT_API_KEY or not settings.LIVEKIT_API_SECRET:
        raise LiveKitConfigurationError("LiveKit API key and secret are not configured.")

    lkapi = api.LiveKitAPI(
        api_key=settings.LIVEKIT_API_KEY,
        api_secret=settings.LIVEKIT_API_SECRET,
    )
    try:
        participant = await lkapi.room.get_participant(api.RoomParticipantIdentity(room=room_name, identity=identity))
        if not participant:
            raise ParticipantNotFoundError(f"Participant {identity} not found in room {room_name}.")

        track_sid = None
        for track in participant.tracks:
            if track.type == api.TrackType.AUDIO:
                track_sid = track.sid
                break

        if track_sid is None:
            raise NoAudioTrackError(f"Participant {identity} has no audio track in room {room_name}.")

        await lkapi.room.mute_published_track(
            api.MuteRoomTrackRequest(
                room=room_name,
                identity=identity,
                track_sid=track_sid,
                muted=True,
            )
        )
    finally:
        await lkapi.aclose()


async def _mute_all_participants(room_name: str, except_identity: str | None = None) -> None:
    if not settings.LIVEKIT_API_KEY or not settings.LIVEKIT_API_SECRET:
        raise LiveKitConfigurationError("LiveKit API key and secret are not configured.")

    lkapi = api.LiveKitAPI(
        api_key=settings.LIVEKIT_API_KEY,
        api_secret=settings.LIVEKIT_API_SECRET,
    )
    try:
        resp = await lkapi.room.list_participants(api.ListParticipantsRequest(room=room_name))
        for participant in resp.participants:
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
                    except Exception:
                        logger.exception(
                            "Failed to mute participant %s in room %s",
                            participant.identity,
                            room_name,
                        )
    finally:
        await lkapi.aclose()


async def _remove_participant(room_name: str, identity: str) -> None:
    if not settings.LIVEKIT_API_KEY or not settings.LIVEKIT_API_SECRET:
        raise LiveKitConfigurationError("LiveKit API key and secret are not configured.")

    lkapi = api.LiveKitAPI(
        api_key=settings.LIVEKIT_API_KEY,
        api_secret=settings.LIVEKIT_API_SECRET,
    )
    try:
        try:
            await lkapi.room.remove_participant(api.RoomParticipantIdentity(room=room_name, identity=identity))
        except Exception as e:
            raise ParticipantNotFoundError(f"Failed to remove participant {identity} from room {room_name}: {e}") from e
    finally:
        await lkapi.aclose()


@async_to_sync
async def mute_participant(room_name: str, identity: str) -> None:
    """Mute a specific participant's audio track."""
    await _mute_participant(room_name, identity)


@async_to_sync
async def mute_all_participants(room_name: str, except_identity: str | None = None) -> None:
    """Mute all participants, optionally skipping one. Logs and continues on individual failures."""
    await _mute_all_participants(room_name, except_identity)


@async_to_sync
async def remove_participant(room_name: str, identity: str) -> None:
    """Remove a participant from the room."""
    await _remove_participant(room_name, identity)
