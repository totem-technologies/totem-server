"""
LiveKit integration helpers.

All LiveKit API calls live here — nowhere else in the app talks to LiveKit.
"""

from __future__ import annotations

import asyncio
import logging

from asgiref.sync import async_to_sync
from django.conf import settings
from livekit import api

from totem.users.models import User

from .schemas import RemoveParticipantPayload, RemoveReason, RoomState

logger = logging.getLogger(__name__)


def _get_api():
    if not settings.LIVEKIT_API_KEY or not settings.LIVEKIT_API_SECRET:
        raise LiveKitConfigurationError("LiveKit API key or secret not configured")
    return api.LiveKitAPI(
        api_key=settings.LIVEKIT_API_KEY,
        api_secret=settings.LIVEKIT_API_SECRET,
    )


async def _get_connected_participants(room_name: str) -> set[str]:
    async with _get_api() as lkapi:
        resp = await lkapi.room.list_participants(api.ListParticipantsRequest(room=room_name))
        return {p.identity for p in resp.participants if p.state != api.ParticipantInfo.State.DISCONNECTED}


async def _publish_state(room_name: str, state: RoomState) -> None:
    async with _get_api() as lkapi:
        await lkapi.room.update_room_metadata(
            update=api.UpdateRoomMetadataRequest(
                room=room_name,
                metadata=state.model_dump_json(),
            )
        )


@async_to_sync
async def get_connected_participants(room_name: str) -> set[str] | None:
    """
    Returns the set of user slugs currently connected to the LiveKit room.
    Returns None when LiveKit is unreachable so callers can distinguish
    "empty room" from "could not check room".
    """
    try:
        return await _get_connected_participants(room_name)
    except api.TwirpError:
        logger.debug("Could not fetch participants for room %s", room_name, exc_info=True)
        return None


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
MAX_PARTICIPANTS = 10


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class LiveKitConfigurationError(Exception):
    """Raised when LiveKit API key/secret are not configured."""


# ---------------------------------------------------------------------------
# Token generation
# ---------------------------------------------------------------------------


def create_access_token(user: User, room_name: str) -> str:
    """
    Create a LiveKit access token for a user to join a session room.
    Raises LiveKitConfigurationError if LiveKit is not configured.
    """
    if not settings.LIVEKIT_API_KEY or not settings.LIVEKIT_API_SECRET:
        raise LiveKitConfigurationError("LiveKit API key and secret are not configured.")

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
                max_participants=MAX_PARTICIPANTS,
            )
        )
    )

    return token.to_jwt()


# ---------------------------------------------------------------------------
# Participant management
# ---------------------------------------------------------------------------


async def _mute_track_for_participant(room_name: str, identity: str, track_type: api.TrackType) -> None:
    """Mute a specific track type (AUDIO or VIDEO) for a participant."""
    async with _get_api() as lkapi:
        participant = await lkapi.room.get_participant(api.RoomParticipantIdentity(room=room_name, identity=identity))
        if not participant:
            return

        track_sid = None
        for track in participant.tracks:
            if track.type == track_type:
                track_sid = track.sid
                break

        if track_sid is None:
            return

        await lkapi.room.mute_published_track(
            api.MuteRoomTrackRequest(
                room=room_name,
                identity=identity,
                track_sid=track_sid,
                muted=True,
            )
        )


async def _mute_track_for_all_participants(
    room_name: str, track_type: api.TrackType, except_identity: str | None = None
) -> None:
    """Mute a specific track type for all participants in a room. Uses asyncio.gather for concurrency."""
    label = "audio" if track_type == api.TrackType.AUDIO else "video"
    async with _get_api() as lkapi:
        resp = await lkapi.room.list_participants(api.ListParticipantsRequest(room=room_name))
        tasks = []
        for participant in resp.participants:
            if except_identity and participant.identity == except_identity:
                continue
            if participant.state == api.ParticipantInfo.State.DISCONNECTED:
                continue
            for track in participant.tracks:
                if track.type == track_type:
                    tasks.append(
                        lkapi.room.mute_published_track(
                            api.MuteRoomTrackRequest(
                                room=room_name,
                                identity=participant.identity,
                                track_sid=track.sid,
                                muted=True,
                            )
                        )
                    )
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                logger.exception("Failed to mute %s for participant in room %s", label, room_name, exc_info=result)


async def _remove_participant(room_name: str, identity: str, reason: RemoveReason = RemoveReason.REMOVE) -> None:
    async with _get_api() as lkapi:
        try:
            await lkapi.room.send_data(
                api.SendDataRequest(
                    room=room_name,
                    topic="lk-participant-removed-topic",
                    data=RemoveParticipantPayload(identity=identity, reason=reason).model_dump_json().encode(),
                    destination_identities=[identity],
                    kind=api.DataPacket.Kind.RELIABLE,
                )
            )
        except Exception:
            logger.exception(
                "Failed to send remove data message to %s in room %s, falling back to hard remove", identity, room_name
            )
            await lkapi.room.remove_participant(api.RoomParticipantIdentity(room=room_name, identity=identity))


@async_to_sync
async def mute_participant(room_name: str, identity: str) -> None:
    """Mute a specific participant's audio track."""
    await _mute_track_for_participant(room_name, identity, api.TrackType.AUDIO)


@async_to_sync
async def mute_all_participants(room_name: str, except_identity: str | None = None) -> None:
    """Mute all participants, optionally skipping one. Logs and continues on individual failures."""
    await _mute_track_for_all_participants(room_name, api.TrackType.AUDIO, except_identity)


@async_to_sync
async def disable_camera_participant(room_name: str, identity: str) -> None:
    """Disable a specific participant's camera track."""
    await _mute_track_for_participant(room_name, identity, api.TrackType.VIDEO)


@async_to_sync
async def disable_camera_all_participants(room_name: str, except_identity: str | None = None) -> None:
    """Disable camera for all participants, optionally skipping one. Logs and continues on individual failures."""
    await _mute_track_for_all_participants(room_name, api.TrackType.VIDEO, except_identity)


@async_to_sync
async def remove_participant(room_name: str, identity: str, reason: RemoveReason = RemoveReason.REMOVE) -> None:
    """Remove a participant from the room."""
    await _remove_participant(room_name, identity, reason)
