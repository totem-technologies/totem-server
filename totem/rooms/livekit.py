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
