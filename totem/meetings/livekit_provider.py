from django.conf import settings
from livekit import api

from totem.users.models import User

from ..circles.models import CircleEvent


def livekit_create_access_token(user: User, event: CircleEvent) -> str:
    """
    Create a LiveKit access token for a user to join a specific event room.

    If the room doesn't exist, it will be created automatically when the user joins.
    """
    if not settings.LIVEKIT_API_KEY or not settings.LIVEKIT_API_SECRET:
        raise ValueError("LiveKit API key and secret are not configured.")

    participant_identity = user.slug
    room_name = event.slug

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
                max_participants=event.attendees.count() + 5,
            )
        )
    )

    return token.to_jwt()
