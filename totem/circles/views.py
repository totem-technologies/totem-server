import datetime
from dataclasses import dataclass
from io import BytesIO

import pytz
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from sentry_sdk import capture_exception

from totem.users import analytics
from totem.users.models import User
from totem.utils.hash import basic_hash
from totem.utils.img_gen import CircleImageParams, generate_circle_image
from totem.utils.utils import is_ajax

from .actions import JoinCircleAction, SubscribeAction
from .filters import (
    upcoming_events_by_author,
)
from .models import Circle, CircleEvent, CircleEventException

ICS_QUERY_PARAM = "key"
AUTO_RSVP_SESSION_KEY = "auto_rsvp"


def _get_circle(slug: str) -> Circle:
    try:
        return Circle.objects.get(slug=slug)
    except Circle.DoesNotExist:
        raise Http404


def _get_circle_event(slug: str) -> CircleEvent:
    try:
        return (
            CircleEvent.objects.select_related("circle", "circle__author")
            .prefetch_related("attendees", "circle__subscribed")
            .get(slug=slug)
        )
    except CircleEvent.DoesNotExist:
        raise Http404


def event_detail(request, event_slug):
    event = _get_circle_event(event_slug)
    circle = event.circle
    return _circle_detail(request, request.user, circle, event)


def detail(request, slug):
    circle = _get_circle(slug)
    event = circle.next_event()
    if not event:
        return _circle_detail(request, request.user, circle, event)
    return redirect("circles:event_detail", event_slug=event.slug)


def _circle_detail(request: HttpRequest, user: User, circle: Circle, event: CircleEvent | None):
    if not circle.published and not user.is_staff:
        raise PermissionDenied

    attending = False
    joinable = False
    subscribed = False
    if user.is_authenticated:
        subscribed = circle.subscribed.contains(user)
        if event:
            attending = event.attendees.contains(user)
            joinable = event.can_join(user)

    other_circles = upcoming_events_by_author(user, circle.author, exclude_event=event)[:6]

    return render(
        request,
        "circles/detail.html",
        {
            "object": circle,
            "attending": attending,
            "joinable": joinable,
            "subscribed": subscribed,
            "event": event,
            "other_circles": other_circles,
        },
    )


def ics_hash(slug, user_ics_key):
    # Hash the slug with the secret key
    # to make the ics key
    return basic_hash(slug + str(user_ics_key))


def _add_or_remove_attendee(user, event: CircleEvent, add: bool):
    if add:
        event.add_attendee(user)
        event.circle.subscribe(user)
    else:
        event.remove_attendee(user)


def rsvp(request: HttpRequest, event_slug):
    if not request.user.is_authenticated:
        request.session[AUTO_RSVP_SESSION_KEY] = event_slug
        return redirect_to_login(request.get_full_path())
    event = _get_circle_event(event_slug)
    error = ""
    if request.POST:
        try:
            with transaction.atomic():
                _add_or_remove_attendee(request.user, event, request.POST.get("action") != "remove")
        except CircleEventException as e:
            error = str(e)
    if is_ajax(request):
        if error:
            return JsonResponse({"error": error}, status=400)
        return JsonResponse({"ok": True})
    else:
        if error:
            messages.error(request, error)
        return redirect("circles:event_detail", event_slug=event.slug)


def events(request):
    return render(request, "circles/events.html")


def spaces(request):
    return render(request, "circles/spaces.html")


@transaction.atomic
def join(request, event_slug):
    token = request.GET.get("token")
    if token:
        try:
            user, params = JoinCircleAction.resolve(token)
            token_event_slug = params["event_slug"]
            if token_event_slug != event_slug:
                raise PermissionDenied
        except Exception:
            messages.error(
                request, "Invalid or expired link. If you think this is an error, please contact us: help@totem.org."
            )
            return redirect("circles:event_detail", event_slug=event_slug)
    elif request.user.is_authenticated:
        user = request.user
    else:
        return redirect_to_login(request.get_full_path())

    event = _get_circle_event(event_slug)
    if event.can_join(user):
        event.joined.add(user)
        analytics.event_joined(user, event)
        return redirect(event.meeting_url, permanent=False)

    if event.started():
        messages.info(request, "This event has already started.")
    else:
        messages.info(request, "Cannot join at this time. Please try again later.")
    return redirect("circles:event_detail", event_slug=event.slug)


@transaction.atomic
def subscribe(request: HttpRequest, slug: str):
    token = request.GET.get("token")

    if request.POST:
        user = request.user
        if not user.is_authenticated:
            raise PermissionDenied
        sub = request.POST.get("action") == "subscribe"
    elif token:
        try:
            user, params = SubscribeAction.resolve(token)
            sub = params["subscribe"]
            slug = params["circle_slug"]
        except Exception as e:
            capture_exception(e)
            messages.error(request, "Invalid or expired link. If you think this is an error, please contact us.")
            return redirect("circles:detail", slug=slug)
    else:
        return redirect("circles:detail", slug=slug)

    circle = _get_circle(slug)
    if sub:
        circle.subscribe(user)
        message = "You are now subscribed to this Space."
    else:
        circle.unsubscribe(user)
        message = "You are now unsubscribed from this Space."

    if is_ajax(request):
        return HttpResponse("ok")

    messages.add_message(request, messages.SUCCESS, message)
    return redirect("circles:detail", slug=slug)


def calendar(request: HttpRequest, event_slug: str):
    event = _get_circle_event(event_slug)
    user = request.user

    if not event.circle.published and not user.is_staff:  # type: ignore
        raise PermissionDenied

    return render(request, "circles/calendaradd.html", {"event": event})


def event_social(request: HttpRequest, event_slug: str):
    event = _get_circle_event(event_slug)
    user: User = request.user
    # start time in pst
    start_time_pst = event.start.astimezone(pytz.timezone("US/Pacific")).strftime("%I:%M %p") + " PST"
    # start time in est
    start_time_est = event.start.astimezone(pytz.timezone("US/Eastern")).strftime("%I:%M %p") + " EST"

    if not event.circle.published and not user.is_staff:  # type: ignore
        raise PermissionDenied

    return render(
        request,
        "circles/social.html",
        {
            "object": event.circle,
            "event": event,
            "start_time_pst": start_time_pst,
            "start_time_est": start_time_est,
        },
    )


@dataclass
class SocialImage:
    height: int
    width: int


def event_social_img(request: HttpRequest, event_slug: str, image_format: str):
    image_size = {
        "square": SocialImage(height=1080, width=1080),
        "2to1": SocialImage(width=1280, height=640),
        "4to5": SocialImage(width=1080, height=1350),
    }.get(image_format)
    if not image_size:
        raise Http404

    event = _get_circle_event(event_slug)
    pst: datetime.datetime = event.start.astimezone(pytz.timezone("US/Pacific"))
    est: datetime.datetime = event.start.astimezone(pytz.timezone("US/Eastern"))
    # start time in pst
    start_day_pst: str = pst.strftime("%B %d, %Y")
    start_time_pst: str = pst.strftime("%-I:%M %p") + " PST"
    # start time in est
    start_day_est: str = est.strftime("%B %d, %Y")
    start_time_est: str = est.strftime("%-I:%M %p") + " EST"
    if start_day_pst != start_day_est:
        start_time_est = f"{start_time_est}+1"
    buffer = BytesIO()
    _make_social_img(event, start_day_pst, start_time_pst, start_time_est, image_size).save(
        buffer, "JPEG", optimize=True
    )
    response = HttpResponse(content_type="image/jpeg")
    response["Cache-Control"] = "max-age=600"  # Cache for 10 minutes (600 seconds)
    response.write(buffer.getvalue())
    return response


def _make_social_img(event: CircleEvent, start_day, start_time_pst, start_time_est, image_size: SocialImage):
    title = event.circle.title
    subtitle = event.circle.subtitle
    if event.title:
        title = event.title
        subtitle = event.circle.title

    background_url = f"{settings.BASE_DIR}/totem/static/images/circles/default-bg.jpg"
    if event.circle.image:
        background_url = event.circle.image.url
        if background_url.startswith("/"):
            background_url = f"totem/{background_url}"

    author_profile_url = f"{settings.BASE_DIR}/totem/static/images/default-avatar.jpg"
    if event.circle.author.profile_image:
        author_profile_url = event.circle.author.profile_image.url
        if author_profile_url.startswith("/"):
            author_profile_url = f"totem/{author_profile_url}"

    params = CircleImageParams(
        background_path=background_url,
        author_img_path=author_profile_url,
        author_name=event.circle.author.name,
        title=title,
        subtitle=subtitle,
        day=start_day,
        time_pst=start_time_pst,
        time_est=start_time_est,
        width=image_size.width,
        height=image_size.height,
    )
    return generate_circle_image(params)
