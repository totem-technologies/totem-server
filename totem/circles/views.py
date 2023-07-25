import base64
import dataclasses

import faker
from django.http import Http404, HttpResponse
from django.shortcuts import render

from .calendar import calendar

fake = faker.Faker()


@dataclasses.dataclass
class Circle:
    title: str
    subtitle: str
    tags: list[str]
    description: str
    image_url: str
    author: str
    author_url: str
    date_modified: str
    published: bool
    author_image_url: str
    slug: str
    pk: int
    price: str
    type: str
    datetime: str
    duration: str
    google_url: str

    @property
    def event_id(self):
        # URL from when you edit an event in Google Calendar
        data = self.google_url.split("/")[-1].split("?")[0]
        # Add missing padding, if any
        missing_padding = len(data) % 4
        if missing_padding:
            data += "=" * (4 - missing_padding)
        # Decode the Base64 encoded string at the end of the URL
        # and extract the event ID
        # Decoded string looks like:
        # 51h15rb48o1ighm3rn79dn6vhi_20210729T230000Z {CALENDAR_ID}
        # 51h15rb48o1ighm3rn79dn6vhi is the event ID
        return base64.b64decode(data).decode("utf-8").split(" ")[0].split("_")[0]

    @property
    def ical_uuid(self):
        # Add @google.com to make the ical uuid
        return self.event_id + "@google.com"


circles = {
    "test": Circle(
        title=fake.sentence(),
        subtitle=fake.sentence(),
        tags=["tag1", "tag2", "tag3"],
        description=fake.paragraph(100),
        image_url="https://picsum.photos/seed/picsum/200/300",
        author=fake.name(),
        author_url="https://picsum.photos/seed/picsum/200/300",
        date_modified="2021-01-01",
        published=True,
        author_image_url="https://picsum.photos/seed/picsum/300",
        slug="circle-slug",
        pk=1,
        price="Free",
        type="Circle",
        datetime="2021-01-01",
        duration="1 hour",
        google_url="https://calendar.google.com/calendar/u/0/r/eventedit/NTFoMTVyYjQ4bzFpZ2htM3JuNzlkbjZ2aGlfMjAyMzA3MjlUMjMwMDAwWiBjX2RkZjQ0NThiMzc1YTFkMjgzODlhZWU5M2VkMjM0YWMxYjUxZWU5OGVkMzdkMDlhOGEyMjUwOWE5NTBiYWMxMTVAZw",
    ),
}


def detail(request, slug):
    try:
        circle = circles[slug]
    except KeyError:
        raise Http404
    return render(request, "circles/detail.html", {"object": circle})


def ics(request, slug):
    try:
        circle = circles[slug]
    except KeyError:
        raise Http404
    ics = calendar.get_event_ical(circle.ical_uuid)
    response = HttpResponse(ics, content_type="text/calendar; charset=utf-8")
    response["Content-Length"] = len(ics)
    response["Content-Disposition"] = "attachment; filename=event.ics"
    return response
