"""
LiveKit integration helpers.

All LiveKit API calls live here — nowhere else in the app talks to LiveKit.
"""

from __future__ import annotations

from .schemas import RoomState


def get_connected_participants(room_id: int) -> set[str]:
    """
    Calls LiveKit's ListParticipants API to get the set of user slugs
    currently connected to the room.
    """
    # TODO: implement — call livekit RoomService.ListParticipants,
    # extract participant identities (which should be user slugs)
    raise NotImplementedError


def publish_state(room_id: int, state: RoomState) -> None:
    """
    Publishes the state snapshot to LiveKit room metadata.
    Fire-and-forget — failures here don't roll back the transition.
    """
    # TODO: implement — call livekit RoomService.UpdateRoomMetadata
    raise NotImplementedError
