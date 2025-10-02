import logging

from django.shortcuts import get_object_or_404
from ninja import Router
from ninja.errors import AuthorizationError

from totem.circles.models import CircleEvent
from totem.meetings.livekit_provider import livekit_create_access_token
from totem.meetings.schemas import LivekitTokenResponseSchema
from totem.users.models import User

meetings_router = Router()


@meetings_router.get(
    "/event/{event_slug}/token",
    response={200: LivekitTokenResponseSchema, 403: str, 404: str},
    tags=["meetings"],
    url_name="get_livekit_token",
)
def get_livekit_token(request, event_slug: str):
    user: User = request.auth
    event: CircleEvent = get_object_or_404(CircleEvent, slug=event_slug)

    is_joinable = event.can_join(user=user)
    if not is_joinable:
        logging.warning("User %s attempted to join non-joinable event %s", user.slug, event.slug)
        raise AuthorizationError(message="Event is not joinable at this time.")

    
    token = livekit_create_access_token(user, event)
    return LivekitTokenResponseSchema(token=token)
