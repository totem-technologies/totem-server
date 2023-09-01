from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from totem.utils.hash import basic_hash

from .calendar import calendar
from .models import Circle, CircleEvent, CircleEventException

User = get_user_model()


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


def detail(request, slug, event_slug=None):
    circle = _get_circle(slug)
    if event_slug is not None:
        try:
            event = circle.events.get(slug=event_slug)
        except CircleEvent.DoesNotExist:
            raise Http404
    else:
        event = circle.next_event()
    if not circle.published and not request.user.is_staff:
        raise Http404
    if request.user.is_authenticated:
        attending = event.attendees.contains(request.user)
    else:
        attending = False
    ics_url = ""
    if attending:
        ih = ics_hash(slug, request.user.ics_key)
        ics_url = (
            request.build_absolute_uri(reverse("circles:ics", kwargs={"slug": slug})) + f"?{ICS_QUERY_PARAM}={ih}"
        )
        ics_url = ics_url.replace("http://", "https://")

    return render(
        request,
        "circles/detail.html",
        {
            "object": circle,
            "attending": attending,
            "ics_url": ics_url,
            "event": event,
            "other_events": circle.other_events(),
        },
    )


def ics(request, slug):
    # cannot depend on user since this is a public URL, accessed by a calendar app
    circle = _get_circle(slug)
    if not circle.published and not request.user.is_staff:
        raise Http404
    # check the ics key
    ih = request.GET.get(ICS_QUERY_PARAM)
    if not ih:
        raise Http404
    attendees = circle.attendees.all()
    for attendee in attendees:
        if ih == ics_hash(slug, attendee.ics_key):
            break
        raise Http404
    ics = calendar.get_event_ical(circle.ical_uuid)
    # add REFRESH-INTERVAL
    response = HttpResponse(ics, content_type="text/calendar; charset=utf-8")
    response["Content-Length"] = len(ics)
    response["Content-Disposition"] = "attachment; filename=event.ics"
    return response


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
    return redirect("circles:detail", slug=event.circle.slug)


class CircleListItem:
    def __init__(self, circle):
        self.circle: Circle = circle


def list(request):
    events = CircleEvent.objects.filter(start__gte=timezone.now())
    if request.user.is_staff:
        events = events.all()
    else:
        events = events.filter(circle__published=True)
    events.order_by("start")
    circles = []
    for event in events:
        if event.circle in circles:
            continue
        circles.append(event.circle)
    circle_list_items = [CircleListItem(circle) for circle in circles]
    return render(request, "circles/list.html", {"circles": circle_list_items})
