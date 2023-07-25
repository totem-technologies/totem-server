from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render

User = get_user_model()

import faker

from .calendar import calendar
from .models import Circle

fake = faker.Faker()


test_circle = Circle(
    title=fake.sentence(),
    subtitle=fake.sentence(),
    tags=["tag1", "tag2", "tag3"],
    description=fake.paragraph(100),
    image_url="https://picsum.photos/seed/picsum/200/300",
    author=User.objects.get(id=1),
    published=True,
    slug="circle-slug",
    pk=1,
    price="Free",
    duration="1 hour",
    google_url="https://calendar.google.com/calendar/u/0/r/eventedit/NTFoMTVyYjQ4bzFpZ2htM3JuNzlkbjZ2aGlfMjAyMzA3MjlUMjMwMDAwWiBjX2RkZjQ0NThiMzc1YTFkMjgzODlhZWU5M2VkMjM0YWMxYjUxZWU5OGVkMzdkMDlhOGEyMjUwOWE5NTBiYWMxMTVAZw",
)


def _get_circle(slug: str) -> Circle:
    if slug == "test":
        circle = test_circle
    else:
        try:
            circle = Circle.objects.get(slug=slug)
        except Circle.DoesNotExist:
            raise Http404
    return circle


def detail(request, slug):
    circle = _get_circle(slug)
    if not circle.published and not request.user.is_staff:
        raise Http404
    return render(
        request,
        "circles/detail.html",
        {"object": circle, "attending": circle.attendees.contains(request.user)},
    )


@login_required
def ics(request, slug):
    circle = _get_circle(slug)
    if not circle.published and not request.user.is_staff:
        raise Http404
    ics = calendar.get_event_ical(circle.ical_uuid)
    # add REFRESH-INTERVAL
    response = HttpResponse(ics, content_type="text/calendar; charset=utf-8")
    response["Content-Length"] = len(ics)
    response["Content-Disposition"] = "attachment; filename=event.ics"
    return response


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
