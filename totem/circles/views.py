import hashlib

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse

User = get_user_model()

from .calendar import calendar
from .models import Circle

ICS_QUERY_PARAM = "key"

# test_circle = Circle(
#     title=fake.sentence(),
#     subtitle=fake.sentence(),
#     tags=["tag1", "tag2", "tag3"],
#     description=fake.paragraph(100),
#     author=User.objects.get(id=1),
#     published=True,
#     slug="circle-slug",
#     pk=1,
#     price="Free",
#     duration="1 hour",
#     google_url="https://calendar.google.com/calendar/u/0/r/eventedit/NTFoMTVyYjQ4bzFpZ2htM3JuNzlkbjZ2aGlfMjAyMzA3MjlUMjMwMDAwWiBjX2RkZjQ0NThiMzc1YTFkMjgzODlhZWU5M2VkMjM0YWMxYjUxZWU5OGVkMzdkMDlhOGEyMjUwOWE5NTBiYWMxMTVAZw",
# )


def _get_circle(slug: str) -> Circle:
    try:
        return Circle.objects.get(slug=slug)
    except Circle.DoesNotExist:
        raise Http404


def detail(request, slug):
    circle = _get_circle(slug)
    if not circle.published and not request.user.is_staff:
        raise Http404
    attending = circle.attendees.contains(request.user)
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
        {"object": circle, "attending": circle.attendees.contains(request.user), "ics_url": ics_url},
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
    return hashlib.blake2b((slug + str(user_ics_key)).encode("utf-8"), digest_size=10).hexdigest()


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
