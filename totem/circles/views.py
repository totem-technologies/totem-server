from datetime import datetime

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from totem.utils.hash import basic_hash

from .calendar import calendar
from .models import Circle

User = get_user_model()


ICS_QUERY_PARAM = "key"


def _get_circle(slug: str) -> Circle:
    try:
        return Circle.objects.get(slug=slug)
    except Circle.DoesNotExist:
        raise Http404


def detail(request, slug):
    circle = _get_circle(slug)
    if not circle.published and not request.user.is_staff:
        raise Http404
    if request.user.is_authenticated:
        attending = circle.attendees.contains(request.user)
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
        {"object": circle, "attending": attending, "ics_url": ics_url},
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
def rsvp(request, slug):
    # user = request.user
    if request.POST:
        circle = _get_circle(slug)
        if not circle.published and not request.user.is_staff:
            raise Http404
        if request.user in circle.attendees.all():
            circle.attendees.remove(request.user)
        else:
            circle.attendees.add(request.user)
        circle.save()
    return redirect("circles:detail", slug=slug)


class CircleListItem:
    def __init__(self, circle, is_attending):
        self.circle = circle
        self.is_attending = is_attending


def list(request):
    circles = Circle.objects.filter(start__gte=datetime.now())
    if request.user.is_staff:
        circles = circles.all()
    else:
        circles = circles.filter(published=True)
    circles.order_by("start")
    if request.user.is_authenticated:
        attending = request.user.attending.all()
        circles = [CircleListItem(circle, circle in attending) for circle in circles]
    else:
        circles = [CircleListItem(circle, False) for circle in circles]
    return render(request, "circles/list.html", {"circles": circles})
