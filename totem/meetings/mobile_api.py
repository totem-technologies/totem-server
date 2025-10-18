import json
import logging

from asgiref.sync import sync_to_async
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404
from ninja import Router
from ninja.errors import AuthorizationError

from totem.circles.models import CircleEvent
from totem.meetings.livekit_provider import livekit_create_access_token, propagate_pass_totem, update_room_metadata
from totem.meetings.room_state import SessionStatus
from totem.meetings.schemas import LivekitTokenResponseSchema
from totem.users.models import User

meetings_router = Router()


@meetings_router.get(
    "/event/{event_slug}/token",
    response={200: LivekitTokenResponseSchema, 403: str, 404: str},
    tags=["meetings"],
    url_name="get_livekit_token",
)
async def get_livekit_token(request, event_slug: str):
    user: User = request.auth

    try:
        event = await sync_to_async(CircleEvent.objects.get)(slug=event_slug)
    except CircleEvent.DoesNotExist:
        return 404, "Event not found"

    is_joinable = await sync_to_async(event.can_join)(user=user)
    if not is_joinable:
        logging.warning("User %s attempted to join non-joinable event %s", user.slug, event.slug)
        return 403, "Event is not joinable at this time."

    speaking_order = await sync_to_async(list)(event.attendees.all())
    await update_room_metadata(
        room_name=event.slug,
        metadata={
            "status": SessionStatus.STARTED,
            "speakingOrder": speaking_order,
            "speakingNow": None,
        },
    )

    token = await livekit_create_access_token(user, event)
    return LivekitTokenResponseSchema(token=token)


@meetings_router.post(
    "/event/{event_slug}/update-metadata",
    tags=["meetings"],
    url_name="update_room_metadata",
)
async def update_room_metadata_endpoint(request, event_slug: str):
    user: User = request.auth
    event: CircleEvent = get_object_or_404(CircleEvent, slug=event_slug)

    if not user.is_staff:
        logging.warning("User %s attempted to update metadata for event %s", user.slug, event.slug)
        raise AuthorizationError(message="Only staff can update room metadata.")

    if request.content_type == "application/json":
        try:
            data = json.loads(request.body.decode("utf-8"))
            await update_room_metadata(
                room_name=event.slug,
                metadata=data,
            )
            return HttpResponse()
        except json.JSONDecodeError:
            return HttpResponseBadRequest("Invalid body.")
    else:
        return HttpResponseBadRequest("Content-Type must be application/json")


@meetings_router.post(
    "/event/{event_slug}/pass-totem",
    tags=["meetings"],
    url_name="pass_totem",
)
async def pass_totem_endpoint(request, event_slug: str):
    user: User = request.auth

    try:
        await propagate_pass_totem(event_slug, user.slug)
        return HttpResponse()
    except ValueError as e:
        raise AuthorizationError(message=str(e))
