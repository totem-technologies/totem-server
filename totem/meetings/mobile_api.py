from django.shortcuts import get_object_or_404
from ninja import Router
from ninja.errors import AuthorizationError

from totem.circles.models import CircleEvent, CircleEventState
from totem.meetings.livekit_provider import livekit_create_access_token
from totem.meetings.schemas import LivekitTokenResponseSchema
from totem.users.models import User

meetings_router = Router()

@meetings_router.get(
    "/event/{event_slug}/token",
    response={200: LivekitTokenResponseSchema, 403: str, 404: str},
    tags=["meetings"],
    url_name="livekit_token",
)
def get_livekit_token(request, event_slug: str):
    user: User = request.auth
    event = get_object_or_404(CircleEvent, slug=event_slug)

    if not event.state(user=user) == CircleEventState.JOINABLE:
        raise AuthorizationError(message="Event is not joinable at this time.")

    if not event.attendees.filter(id=user.slug).exists():
        raise AuthorizationError(message="You have not RSVP'd for this event.")

    try:
        token = livekit_create_access_token(user, event)
        return LivekitTokenResponseSchema(token=token)
    except ValueError as e:
        raise AuthorizationError(message=str(e))