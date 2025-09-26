from django.conf import settings
from livekit import api

from totem.users.models import User

from ..circles.models import CircleEvent


def livekit_create_access_token(user: User, event: CircleEvent) -> str:
    """
    Generates a LiveKit access token for a user to join a specific event room.
    """
    if not settings.LIVEKIT_API_KEY or not settings.LIVEKIT_API_SECRET:
        raise ValueError("LiveKit API key and secret are not configured.")
    
    room_name = event.slug
    participant_identity = user.slug
    
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
    )

    return token.to_jwt()
