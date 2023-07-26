import base64

from django.conf import settings
from django.db import models
from django.urls import reverse
from taggit.managers import TaggableManager

from totem.utils.models import SluggedModel

# Create your models here.


class Circle(SluggedModel):
    title = models.CharField(max_length=255)
    subtitle = models.CharField(max_length=2000)
    tags = TaggableManager()
    description = models.TextField()
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, limit_choices_to={"is_staff": True})
    date_created = models.DateTimeField(auto_now_add=True)
    date_modified = models.DateTimeField(auto_now=True)
    published = models.BooleanField(default=False, help_text="Is this Circle visible?")
    open = models.BooleanField(default=True, help_text="Is this Circle for more attendees?")
    price = models.CharField(max_length=255)
    type = "Circle"
    start = models.DateTimeField()
    duration = models.CharField(max_length=255)
    recurring = models.CharField(max_length=255)
    google_url = models.URLField()
    attendees = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="attending")

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

    def __str__(self):
        return self.title

    def get_absolute_url(self) -> str:
        return reverse("circles:detail", kwargs={"slug": self.slug})

    def number_of_attendees(self):
        return self.attendees.count()

    def attendee_list(self):
        return ", ".join([str(attendee) for attendee in self.attendees.all()])
