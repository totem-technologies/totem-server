import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpRequest
from django.shortcuts import redirect, render
from django.utils import timezone

from totem.users.models import User
from totem.utils.hash import basic_hash

from .models import Circle, CircleEvent, CircleEventException

ICS_QUERY_PARAM = "key"


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


def _circle_detail(request, user: User, circle: Circle, event):
    if not circle.published and not user.is_staff:
        raise Http404

    attending = False
    joinable = False
    subscribed = False
    if user.is_authenticated and event:
        attending = event.attendees.contains(user)
        joinable = event.can_join(user)
        subscribed = circle.subscribed.contains(user)

    # if attending:
    #     ih = ics_hash(slug, request.user.ics_key)
    #     ics_url = (
    #         request.build_absolute_uri(reverse("circles:ics", kwargs={"slug": slug})) + f"?{ICS_QUERY_PARAM}={ih}"
    #     )
    #     ics_url = ics_url.replace("http://", "https://")
    other_events = []
    if event:
        other_events = circle.other_events(event=event)

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


# def ics(request, slug):
#     # cannot depend on user since this is a public URL, accessed by a calendar app
#     circle = _get_circle(slug)
#     if not circle.published and not request.user.is_staff:
#         raise Http404
#     # check the ics key
#     ih = request.GET.get(ICS_QUERY_PARAM)
#     if not ih:
#         raise Http404
#     attendees = circle.attendees.all()
#     for attendee in attendees:
#         if ih == ics_hash(slug, attendee.ics_key):
#             break
#         raise Http404
#     ics = calendar.get_event_ical(circle.ical_uuid)
#     # add REFRESH-INTERVAL
#     response = HttpResponse(ics, content_type="text/calendar; charset=utf-8")
#     response["Content-Length"] = len(ics)
#     response["Content-Disposition"] = "attachment; filename=event.ics"
#     return response


def ics_hash(slug, user_ics_key):
    # Hash the slug with the secret key
    # to make the ics key
    return basic_hash(slug + str(user_ics_key))


@login_required
def rsvp(request, event_slug):
    event = _get_circle_event(event_slug)
    if request.POST:
        try:
            if request.POST.get("action") == "remove":
                event.remove_attendee(request.user)
            else:
                event.add_attendee(request.user)
                event.circle.subscribe(request.user)
        except CircleEventException as e:
            messages.error(request, str(e))
    return redirect("circles:event_detail", event_slug=event.slug)


class CircleEventListItem:
    def __init__(self, event, joinable):
        self.event: CircleEvent = event
        self.joinable: bool = joinable


def list(request):
    events = CircleEvent.objects.filter(start__gte=timezone.now()).order_by("start")
    if not request.user.is_staff:
        events = events.filter(circle__published=True)
    attending_events = []
    if request.user.is_authenticated:
        myevents = request.user.events_attending.filter(
            start__gte=timezone.now() - datetime.timedelta(minutes=60)
        ).order_by("start")
        for event in myevents:
            attending_events.append(CircleEventListItem(event, event.can_join(request.user)))
    return render(request, "circles/list.html", {"circles": events, "attending_events": attending_events})


@login_required
def join(request, event_slug):
    event = _get_circle_event(event_slug)
    user = request.user
    if event.can_join(user):
        event.joined.add(user)
        return redirect(event.meeting_url, permanent=False)
    messages.info(request, "Cannot join at this time.")
    return redirect("circles:event_detail", event_slug=event.slug)


def subscribe(request: HttpRequest, slug: str):
    circle = _get_circle(slug)
    user = request.user

    if request.GET.get("token"):
        return _token_subscribe(request, circle)

    if request.method != "POST":
        return render(request, "circles/subscribed.html", {"circle": circle})

    return_url = request.POST.get("return_url")
    if request.POST.get("action") == "unsubscribe":
        circle.unsubscribe(user)
    else:
        circle.subscribe(user)
    if return_url:
        return redirect(return_url)
    return redirect("circles:detail", slug=slug)


def _token_subscribe(request: HttpRequest, circle: Circle):
    user_slug = request.GET.get("user")
    sent_token = request.GET.get("token")

    if not user_slug or not sent_token:
        raise Http404

    user = User.objects.get(slug=user_slug)
    token = circle.subscribe_token(user)

    if sent_token != token:
        raise Http404

    if request.GET.get("action") == "unsubscribe":
        circle.unsubscribe(user)
        return render(request, "circles/subscribed.html", {"circle": circle, "unsubscribed": True})
    else:
        circle.subscribe(user)
        return render(request, "circles/subscribed.html", {"circle": circle})
