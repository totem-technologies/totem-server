from typing import Any

from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpRequest
from django.shortcuts import redirect, render

from totem.users.models import User
from totem.utils.hash import basic_hash

from .actions import JoinCircleAction, SubscribeAction
from .filters import all_upcoming_recommended_circles, all_upcoming_recommended_events, other_events_in_circle
from .models import Circle, CircleCategory, CircleEvent, CircleEventException

ICS_QUERY_PARAM = "key"
AUTO_RSVP_SESSION_KEY = "auto_rsvp"


def _get_circle(slug: str) -> Circle:
    try:
        return Circle.objects.get(slug=slug)
    except Circle.DoesNotExist:
        raise Http404


def _get_circle_event(slug: str) -> CircleEvent:
    try:
        return CircleEvent.objects.get(slug=slug)
    except CircleEvent.DoesNotExist:
        raise Http404


def event_detail(request, event_slug):
    event = _get_circle_event(event_slug)
    circle = event.circle
    return _circle_detail(request, request.user, circle, event)


def detail(request, slug):
    circle = _get_circle(slug)
    event = circle.next_event()
    return _circle_detail(request, request.user, circle, event)


def _circle_detail(request: HttpRequest, user: User, circle: Circle, event):
    if not circle.published and not user.is_staff:
        raise PermissionDenied

    if user.is_authenticated and request.session.get(AUTO_RSVP_SESSION_KEY):
        event_slug = request.session[AUTO_RSVP_SESSION_KEY]
        del request.session[AUTO_RSVP_SESSION_KEY]
        if event_slug == event.slug:
            _add_or_remove_attendee(user, event, True)
            messages.success(request, "Your spot in this Circle has been reserved.")

    attending = False
    joinable = False
    subscribed = False
    if user.is_authenticated:
        subscribed = circle.subscribed.contains(user)
        if event:
            attending = event.attendees.contains(user)
            joinable = event.can_join(user)

    other_events = []
    if event:
        other_events = other_events_in_circle(user=user, event=event)

    return render(
        request,
        "circles/detail.html",
        {
            "object": circle,
            "attending": attending,
            "joinable": joinable,
            "subscribed": subscribed,
            "event": event,
            "other_events": other_events,
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
    if request.POST:
        try:
            _add_or_remove_attendee(request.user, event, request.POST.get("action") != "remove")
        except CircleEventException as e:
            messages.error(request, str(e))
    return redirect("circles:event_detail", event_slug=event.slug)


class CircleEventListItem:
    def __init__(self, event, joinable):
        self.event: CircleEvent = event
        self.joinable: bool = joinable


def list(request):
    category = request.GET.get("category")
    limit = int(request.GET.get("limit", 9))
    if limit > 100:
        raise ValueError
    events = all_upcoming_recommended_events(request.user, category=category, limit=limit + 1).all()
    context: dict[str, Any] = {"events": events[:limit]}
    context["selected_category"] = category or ""
    categories = [
        {"value": "", "label": "All"},
    ]
    categories_values = CircleCategory.objects.values_list("name", "slug").distinct()
    for category in categories_values:
        categories.append(
            {"value": category[1], "label": category[0]},
        )
    context["categories"] = categories
    context["show_load_more"] = len(events) > limit
    return render(request, "circles/list.html", context=context)


def topic(request, slug):
    category = slug
    limit = int(request.GET.get("limit", 9))
    if limit > 100:
        raise ValueError
    events = all_upcoming_recommended_circles(request.user, category=category, limit=limit + 1).all()
    context: dict[str, Any] = {"events": events[:limit]}
    context["selected_category"] = category or ""
    categories = []
    categories_values = CircleCategory.objects.values_list("name", "slug").distinct()
    for category in categories_values:
        value = category[1]
        if value == slug:
            continue
        categories.append(
            {"value": category[1], "label": category[0]},
        )
    circles = set()
    for event in events:
        circles.add(event.circle)
    context["circles"] = circles
    context["categories"] = categories
    context["show_load_more"] = len(events) > limit
    return render(request, "circles/list.html", context=context)


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
        return redirect(event.meeting_url, permanent=False)

    if event.started():
        messages.info(request, "This event has already started.")
    else:
        messages.info(request, "Cannot join at this time. Please try again later.")
    return redirect("circles:event_detail", event_slug=event.slug)


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
        except Exception:
            messages.error(request, "Invalid or expired link. If you think this is an error, please contact us.")
            return redirect("circles:detail", slug=slug)
    else:
        return redirect("circles:detail", slug=slug)

    circle = _get_circle(slug)
    if sub:
        circle.subscribe(user)
        message = "You are now subscribed to this Circle."
    else:
        circle.unsubscribe(user)
        message = "You are now unsubscribed from this Circle."

    messages.add_message(request, messages.SUCCESS, message)
    return redirect("circles:detail", slug=slug)


def calendar(request: HttpRequest, event_slug: str):
    event = _get_circle_event(event_slug)
    user = request.user

    if not event.circle.published and not user.is_staff:  # type: ignore
        raise PermissionDenied

    return render(request, "circles/calendaradd.html", {"event": event})
