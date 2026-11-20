"""
LiveKit integration helpers.

All LiveKit API calls live here — nowhere else in the app talks to LiveKit.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta

import aiohttp
from asgiref.sync import async_to_sync
from django.conf import settings
from livekit import api

from totem.users.models import User

from .schemas import RemoveParticipantPayload, RemoveReason, RoomState

logger = logging.getLogger(__name__)


def _get_api() -> api.LiveKitAPI:
    if not settings.LIVEKIT_URL or not settings.LIVEKIT_API_KEY or not settings.LIVEKIT_API_SECRET:
        raise LiveKitConfigurationError("LiveKit URL, API key or secret not configured")
    return api.LiveKitAPI(
        url=settings.LIVEKIT_URL,
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
    try:
        await _publish_state(room_name, state)
    except Exception:
        logger.exception("Failed to publish room state for session %s", room_name)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ROOM_EMPTY_TIMEOUT_SECONDS = 60 * 60  # 1 hour
MAX_PARTICIPANTS = 10
WAITING_CONNECTION_LIMIT = 5
ENFORCED_MAX_PARTICIPANTS = MAX_PARTICIPANTS + WAITING_CONNECTION_LIMIT
ACCESS_TOKEN_TTL_SECONDS = 60
PERMISSION_UPDATE_TIMEOUT_SECONDS = 5


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class LiveKitConfigurationError(Exception):
    """Raised when LiveKit API key/secret are not configured."""


class LiveKitPermissionError(Exception):
    """A participant permission operation could not be verified."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@asynccontextmanager
async def _permission_errors() -> AsyncIterator[None]:
    try:
        yield
    except api.TwirpError as exc:
        if exc.code == "not_found":
            # Twirp does not reliably distinguish a missing room from a missing participant.
            code = "room_missing" if "room" in exc.message.lower() else "participant_missing"
        else:
            code = "unavailable"
        raise LiveKitPermissionError(code, str(exc)) from exc
    except TimeoutError as exc:
        raise LiveKitPermissionError("timeout", "LiveKit request timed out") from exc
    except (aiohttp.ClientError, OSError, LiveKitConfigurationError) as exc:
        raise LiveKitPermissionError("unavailable", str(exc)) from exc


@async_to_sync
async def publish_admission_changed(room_name: str, version: int, destinations: list[str]) -> bool:
    """Send a targeted, best-effort hint to refresh admission state."""
    if not destinations:
        return True
    try:
        async with _permission_errors():
            async with asyncio.timeout(PERMISSION_UPDATE_TIMEOUT_SECONDS):
                async with _get_api() as lkapi:
                    await lkapi.room.send_data(
                        api.SendDataRequest(
                            room=room_name,
                            topic="totem.admission.v2",
                            data=json.dumps(
                                {"type": "admission.changed", "session_slug": room_name, "version": version}
                            ).encode(),
                            kind=api.DataPacket.Kind.RELIABLE,
                            destination_identities=list(dict.fromkeys(destinations)),
                        )
                    )
    except LiveKitPermissionError as error:
        if error.code == "room_missing":
            logger.info("Admission notification skipped for session %s: LiveKit room does not exist", room_name)
        else:
            logger.warning("Failed to publish admission change for session %s: %s", room_name, error)
        return False
    return True


@async_to_sync
async def get_admission_participants(room_name: str) -> set[str]:
    """Return raw presence, distinguishing a missing room from a lookup outage."""
    async with _permission_errors():
        async with asyncio.timeout(PERMISSION_UPDATE_TIMEOUT_SECONDS):
            try:
                return await _get_connected_participants(room_name)
            except api.TwirpError as exc:
                # ListParticipants not_found confirms room absence, including before the first join.
                if exc.code == "not_found":
                    return set()
                raise


@async_to_sync
async def get_room_participant_sids(room_name: str) -> dict[str, str]:
    """Return current LiveKit connection SIDs without trusting participant metadata."""
    async with _permission_errors():
        async with asyncio.timeout(PERMISSION_UPDATE_TIMEOUT_SECONDS):
            try:
                async with _get_api() as lkapi:
                    response = await lkapi.room.list_participants(api.ListParticipantsRequest(room=room_name))
            except api.TwirpError as exc:
                if exc.code == "not_found":
                    return {}
                raise
            return {
                participant.identity: participant.sid
                for participant in response.participants
                if participant.state != api.ParticipantInfo.State.DISCONNECTED and participant.sid
            }


# ---------------------------------------------------------------------------
# Token generation
# ---------------------------------------------------------------------------


def create_access_token(
    user: User, room_name: str, *, admitted: bool = True, attributes: dict[str, str] | None = None
) -> str:
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
        .with_ttl(timedelta(seconds=ACCESS_TOKEN_TTL_SECONDS))
        .with_grants(
            api.VideoGrants(
                room=room_name,
                room_join=True,
                room_admin=False,
                can_publish=admitted,
                can_subscribe=admitted,
                can_publish_data=admitted,
                can_update_own_metadata=False,
                hidden=False,
            )
        )
        .with_room_config(
            config=api.RoomConfiguration(
                name=room_name,
                empty_timeout=ROOM_EMPTY_TIMEOUT_SECONDS,
                max_participants=ENFORCED_MAX_PARTICIPANTS if settings.SERVER_ENFORCED_ADMISSION else MAX_PARTICIPANTS,
            )
        )
    )

    if attributes is not None:
        token.with_attributes(attributes)
    return token.to_jwt()


# ---------------------------------------------------------------------------
# Participant management
# ---------------------------------------------------------------------------


def _require_connected(participant: api.ParticipantInfo) -> None:
    if not participant or not participant.sid or participant.state == api.ParticipantInfo.State.DISCONNECTED:
        raise LiveKitPermissionError("participant_missing", "Participant is not connected")


@async_to_sync
async def get_participant_snapshot(room_name: str, identity: str) -> api.ParticipantInfo:
    async with _permission_errors():
        async with asyncio.timeout(PERMISSION_UPDATE_TIMEOUT_SECONDS):
            async with _get_api() as lkapi:
                participant = await lkapi.room.get_participant(
                    api.RoomParticipantIdentity(room=room_name, identity=identity)
                )
                _require_connected(participant)
                return participant


@async_to_sync
async def update_participant_permissions(
    room_name: str,
    identity: str,
    *,
    admitted: bool,
    expected_sid: str | None = None,
    attributes: dict[str, str] | None = None,
) -> api.ParticipantInfo:
    async with _permission_errors():
        async with asyncio.timeout(PERMISSION_UPDATE_TIMEOUT_SECONDS):
            async with _get_api() as lkapi:
                lookup = api.RoomParticipantIdentity(room=room_name, identity=identity)
                before = await lkapi.room.get_participant(lookup)
                _require_connected(before)
                if expected_sid is not None and before.sid != expected_sid:
                    raise LiveKitPermissionError("identity_replaced", "Participant connection has changed")

                permission = api.ParticipantPermission(
                    can_publish=admitted,
                    can_subscribe=admitted,
                    can_publish_data=admitted,
                    can_update_metadata=False,
                    hidden=False,
                    recorder=False,
                    agent=False,
                    can_subscribe_metrics=False,
                    can_manage_agent_session=False,
                )
                update = api.UpdateParticipantRequest(room=room_name, identity=identity, permission=permission)
                if attributes is not None:
                    update.attributes.update(attributes)
                await lkapi.room.update_participant(update)
                after = await lkapi.room.get_participant(lookup)
                _require_connected(after)
                if after.sid != before.sid:
                    raise LiveKitPermissionError("identity_replaced", "Participant connection has changed")
                if not after.HasField("permission") or after.permission != permission:
                    raise LiveKitPermissionError("permission_mismatch", "Participant permissions were not applied")
                return after


async def _hard_disconnect_participant(room_name: str, identity: str) -> None:
    async with _permission_errors():
        async with asyncio.timeout(PERMISSION_UPDATE_TIMEOUT_SECONDS):
            async with _get_api() as lkapi:
                await lkapi.room.remove_participant(
                    api.RoomParticipantIdentity(room=room_name, identity=identity, revoke_token_ts=int(time.time()))
                )


hard_disconnect_participant = async_to_sync(_hard_disconnect_participant)


async def _mute_track_for_participant(room_name: str, identity: str, track_source: api.TrackSource) -> None:
    """Mute a participant's track by source (MICROPHONE or CAMERA).

    Matching on source, not type, so screen-share tracks (also AUDIO/VIDEO
    typed) are left alone.
    """
    async with _get_api() as lkapi:
        participant = await lkapi.room.get_participant(api.RoomParticipantIdentity(room=room_name, identity=identity))
        if not participant:
            return

        track_sid = None
        for track in participant.tracks:
            if track.source == track_source:
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
    room_name: str,
    track_source: api.TrackSource,
    except_identity: str | None = None,
    identities: set[str] | None = None,
) -> None:
    """Mute tracks of a given source for all participants in a room. Uses asyncio.gather for concurrency."""
    label = api.TrackSource.Name(track_source).lower()
    async with _get_api() as lkapi:
        resp = await lkapi.room.list_participants(api.ListParticipantsRequest(room=room_name))
        tasks = []
        for participant in resp.participants:
            if (except_identity and participant.identity == except_identity) or (
                identities is not None and participant.identity not in identities
            ):
                continue
            if participant.state == api.ParticipantInfo.State.DISCONNECTED:
                continue
            for track in participant.tracks:
                if track.source == track_source:
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
    if settings.SERVER_ENFORCED_ADMISSION:
        # LiveKit has no compare-and-swap by SID; a concurrent explicit re-admission
        # can race this identity-based removal.
        await _hard_disconnect_participant(room_name, identity)
        return
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
    """Mute a specific participant's microphone track."""
    await _mute_track_for_participant(room_name, identity, api.TrackSource.MICROPHONE)


@async_to_sync
async def mute_all_participants(
    room_name: str, except_identity: str | None = None, identities: set[str] | None = None
) -> None:
    """Mute all participants, optionally skipping one. Logs and continues on individual failures."""
    await _mute_track_for_all_participants(room_name, api.TrackSource.MICROPHONE, except_identity, identities)


@async_to_sync
async def disable_camera_participant(room_name: str, identity: str) -> None:
    """Disable a specific participant's camera track."""
    await _mute_track_for_participant(room_name, identity, api.TrackSource.CAMERA)


@async_to_sync
async def remove_participant(room_name: str, identity: str, reason: RemoveReason = RemoveReason.REMOVE) -> None:
    """Remove a participant from the room."""
    await _remove_participant(room_name, identity, reason)
