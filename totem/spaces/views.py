import datetime
from dataclasses import dataclass

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
from totem.utils.img_gen import SpaceImageParams, generate_space_image
from totem.utils.utils import is_ajax

from .actions import JoinSessionAction, SubscribeSpaceAction
from .filters import (
    upcoming_sessions_by_author,
)
from .models import Session, SessionException, Space

ICS_QUERY_PARAM = "key"
AUTO_RSVP_SESSION_KEY = "auto_rsvp"


def _get_space(slug: str) -> Space:
    try:
        return Space.objects.get(slug=slug)
    except Space.DoesNotExist:
        raise Http404


def _get_session(slug: str) -> Session:
    try:
        return (
            Session.objects.select_related("space", "space__author")
            .prefetch_related("attendees", "space__subscribed")
            .get(slug=slug)
        )
    except Session.DoesNotExist:
        raise Http404


def session_detail(request, session_slug):
    session = _get_session(session_slug)
    space = session.space
    return _space_detail(request, request.user, space, session)


def detail(request, slug):
    space = _get_space(slug)
    session = space.next_session()
    if not session:
        return _space_detail(request, request.user, space, session)
    return redirect("spaces:session_detail", session_slug=session.slug)


def _space_detail(request: HttpRequest, user: User, space: Space, session: Session | None):
    if not space.published and not user.is_staff:
        raise PermissionDenied

    attending = False
    joinable = False
    subscribed = False
    if user.is_authenticated:
        subscribed = space.subscribed.contains(user)
        if session:
            attending = session.attendees.contains(user)
            joinable = session.can_join(user)

    other_spaces = upcoming_sessions_by_author(user, space.author, exclude_event=session)[:6]

    return render(
        request,
        "spaces/detail.html",
        {
            "object": space,
            "attending": attending,
            "joinable": joinable,
            "subscribed": subscribed,
            "session": session,
            "other_spaces": other_spaces,
        },
    )


def ics_hash(slug, user_ics_key):
    # Hash the slug with the secret key
    # to make the ics key
    return basic_hash(slug + str(user_ics_key))


def _add_or_remove_attendee(user, session: Session, add: bool):
    if add:
        session.add_attendee(user)
        session.space.subscribe(user)
    else:
        session.remove_attendee(user)


def rsvp(request: HttpRequest, session_slug):
    if not request.user.is_authenticated:
        request.session[AUTO_RSVP_SESSION_KEY] = session_slug
        return redirect_to_login(request.get_full_path())
    session = _get_session(session_slug)
    error = ""
    if request.POST:
        try:
            with transaction.atomic():
                _add_or_remove_attendee(request.user, session, request.POST.get("action") != "remove")
        except SessionException as e:
            error = str(e)
    if is_ajax(request):
        if error:
            return JsonResponse({"error": error}, status=400)
        return JsonResponse({"ok": True})
    else:
        if error:
            messages.error(request, error)
        return redirect("spaces:session_detail", session_slug=session.slug)


def sessions(request):
    return render(request, "spaces/sessions.html")


def spaces(request):
    return render(request, "spaces/spaces.html")


@transaction.atomic
def join(request, session_slug):
    token = request.GET.get("token")
    if token:
        try:
            user, params = JoinSessionAction.resolve(token)
            token_session_slug = params.get("session_slug") or params.get("event_slug")
            if token_session_slug is None:
                raise PermissionDenied
            if token_session_slug != session_slug:
                raise PermissionDenied
        except Exception:
            messages.error(
                request, "Invalid or expired link. If you think this is an error, please contact us: help@totem.org."
            )
            return redirect("spaces:session_detail", session_slug=session_slug)
    elif request.user.is_authenticated:
        user = request.user
    else:
        return redirect_to_login(request.get_full_path())

    session = _get_session(session_slug)
    if session.can_join(user):
        session.joined.add(user)
        analytics.event_joined(user, session)
        return redirect(session.meeting_url, permanent=False)

    if session.started():
        messages.info(request, "This session has already started.")
    else:
        messages.info(request, "Cannot join at this time. Please try again later.")
    return redirect("spaces:session_detail", session_slug=session.slug)


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
            user, params = SubscribeSpaceAction.resolve(token)
            sub = params["subscribe"]
            slug = params.get("space_slug") or params.get("circle_slug") or slug
        except Exception as e:
            capture_exception(e)
            messages.error(request, "Invalid or expired link. If you think this is an error, please contact us.")
            return redirect("spaces:detail", slug=slug)
    else:
        return redirect("spaces:detail", slug=slug)
    space = _get_space(slug)
    if sub:
        space.subscribe(user)
        message = "You are now subscribed to this Space."
    else:
        space.unsubscribe(user)
        message = "You are now unsubscribed from this Space."

    if is_ajax(request):
        return HttpResponse("ok")

    messages.add_message(request, messages.SUCCESS, message)
    return redirect("spaces:detail", slug=slug)


def calendar(request: HttpRequest, session_slug: str):
    session = _get_session(session_slug)
    user = request.user

    if not session.space.published and not user.is_staff:  # type: ignore
        raise PermissionDenied

    return render(request, "spaces/calendaradd.html", {"event": session, "session": session})


def session_social(request: HttpRequest, session_slug: str):
    session = _get_session(session_slug)
    user: User = request.user  # type: ignore
    # start time in pst
    start_time_pst = session.start.astimezone(pytz.timezone("US/Pacific")).strftime("%I:%M %p") + " PST"
    # start time in est
    start_time_est = session.start.astimezone(pytz.timezone("US/Eastern")).strftime("%I:%M %p") + " EST"

    if not session.space.published and not user.is_staff:  # type: ignore
        raise PermissionDenied

    return render(
        request,
        "spaces/social.html",
        {
            "object": session.space,
            "event": session,
            "session": session,
            "start_time_pst": start_time_pst,
            "start_time_est": start_time_est,
        },
    )


@dataclass
class SocialImage:
    height: int
    width: int


def session_social_img(request: HttpRequest, session_slug: str, image_format: str):
    image_size = {
        "square": SocialImage(height=1080, width=1080),
        "2to1": SocialImage(width=1280, height=640),
        "4to5": SocialImage(width=1080, height=1350),
    }.get(image_format)
    if not image_size:
        raise Http404

    session = _get_session(session_slug)
    pst: datetime.datetime = session.start.astimezone(pytz.timezone("US/Pacific"))
    est: datetime.datetime = session.start.astimezone(pytz.timezone("US/Eastern"))
    # start time in pst
    start_day_pst: str = pst.strftime("%B %d, %Y")
    start_time_pst: str = pst.strftime("%-I:%M %p") + " PST"
    # start time in est
    start_day_est: str = est.strftime("%B %d, %Y")
    start_time_est: str = est.strftime("%-I:%M %p") + " EST"
    if start_day_pst != start_day_est:
        start_time_est = f"{start_time_est}+1"
    image = _make_social_img(session, start_day_pst, start_time_pst, start_time_est, image_size)
    response = HttpResponse(content_type="image/jpeg")
    response["Cache-Control"] = "max-age=600"  # Cache for 10 minutes (600 seconds)
    response.write(image.to_jpeg())
    return response


def _make_social_img(session: Session, start_day, start_time_pst, start_time_est, image_size: SocialImage):
    title = session.space.title
    subtitle = session.space.subtitle
    if session.title:
        title = session.title
        subtitle = session.space.title

    background_url = f"{settings.BASE_DIR}/totem/static/images/spaces/default-bg.jpg"
    if session.space.image:
        background_url = session.space.image.url
        if background_url.startswith("/"):
            background_url = f"totem/{background_url}"

    author_profile_url = f"{settings.BASE_DIR}/totem/static/images/default-avatar.jpg"
    if session.space.author.profile_image:
        author_profile_url = session.space.author.profile_image.url
        if author_profile_url.startswith("/"):
            author_profile_url = f"totem/{author_profile_url}"

    params = SpaceImageParams(
        background_path=background_url,
        author_img_path=author_profile_url,
        author_name=session.space.author.name,
        title=title,
        subtitle=subtitle,
        day=start_day,
        time_pst=start_time_pst,
        time_est=start_time_est,
        width=image_size.width,
        height=image_size.height,
    )
    return generate_space_image(params)


# Legacy redirect for old /spaces/event/<slug>/ URLs
def event_detail_redirect(request: HttpRequest, event_slug: str):
    return redirect("spaces:session_detail", session_slug=event_slug, permanent=True)
