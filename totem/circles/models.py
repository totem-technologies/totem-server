import datetime
import time
from enum import Enum
from typing import TYPE_CHECKING

import markdown
from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models.query import QuerySet
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from imagekit import ImageSpec
from imagekit.models import ProcessedImageField
from imagekit.processors import ResizeToFit
from taggit.managers import TaggableManager

from totem.email.emails import send_notify_circle_advertisement, send_notify_circle_starting
from totem.utils.hash import basic_hash
from totem.utils.md import MarkdownField, MarkdownMixin
from totem.utils.models import AdminURLMixin, SluggedModel
from totem.utils.utils import full_url

from .calendar import calendar

if TYPE_CHECKING:
    from totem.users.models import User


class CircleEventState(Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    JOINABLE = "JOINABLE"
    ENDED = "ENDED"
    STARTED = "STARTED"
    CANCELLED = "CANCELLED"


# Create your models here.
class CircleImageSpec(ImageSpec):
    processors = [ResizeToFit(1500, 1500)]
    format = "JPEG"
    options = {"quality": 80, "optimize": True}


def upload_to_id_image(instance, filename: str):
    extension = filename.split(".")[-1]
    epoch_time = int(time.time())
    new_filename = basic_hash(f"{filename}-{epoch_time}")
    user_slug = instance.author.slug
    return f"circles/{user_slug}/{new_filename}.{extension}"


class Circle(AdminURLMixin, MarkdownMixin, SluggedModel):
    title = models.CharField(max_length=255)
    subtitle = models.CharField(max_length=2000)
    image = ProcessedImageField(
        blank=True,
        null=True,
        upload_to=upload_to_id_image,
        spec=CircleImageSpec,  # type: ignore
        help_text="Image for the Circle, must be under 5mb",
    )
    tags = TaggableManager()
    content = MarkdownField(default="")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        limit_choices_to={"is_staff": True},
        related_name="created_circles",
    )
    published = models.BooleanField(default=False, help_text="Is this Circle visible?")
    open = models.BooleanField(default=True, help_text="Is this Circle for more attendees?")
    price = models.IntegerField(
        default=0,
        help_text="Price in USD dollars. If you want to offer this Circle for free, enter 0.",
        verbose_name="Price (USD)",
        validators=[
            MinValueValidator(0, message="Price must be greater than or equal to 0"),
            MaxValueValidator(1000, message="Price must be less than or equal to 1000"),
        ],
    )
    recurring = models.CharField(max_length=255, help_text="Example: Every Tuesday at 5pm")
    subscribed = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="subscribed_circles")
    events: QuerySet["CircleEvent"]

    def __str__(self):
        return self.title

    def get_absolute_url(self) -> str:
        return reverse("circles:detail", kwargs={"slug": self.slug})

    def subscribed_list(self):
        return ", ".join([str(attendee.email) for attendee in self.subscribed.all()])

    def next_event(self):
        return self.events.filter(start__gte=timezone.now()).order_by("start").first()

    def other_events(self, event: "CircleEvent"):
        return self.events.filter(start__gte=timezone.now()).exclude(slug=event.slug).order_by("start")[:10]

    def is_free(self):
        return self.price == 0

    def subscribe(self, user):
        return self.subscribed.add(user)

    def unsubscribe(self, user):
        return self.subscribed.remove(user)

    def subscribe_token(self, user):
        return basic_hash(f"{self.slug}-{user.email}-{user.api_key}")


class CircleEvent(AdminURLMixin, MarkdownMixin, SluggedModel):
    open = models.BooleanField(default=True, help_text="Is this Circle for more attendees?")
    cancelled = models.BooleanField(default=False, help_text="Is this Circle cancelled?")
    start = models.DateTimeField(default=timezone.now)
    duration_minutes = models.IntegerField(_("Minutes"), default=60)
    attendees = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="events_attending")
    joined = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="events_joined")
    seats = models.IntegerField(default=8)
    circle = models.ForeignKey(Circle, on_delete=models.CASCADE, related_name="events")
    meeting_url = models.CharField(max_length=255, blank=True)
    notified = models.BooleanField(default=False)
    advertised = models.BooleanField(default=False)

    def get_absolute_url(self) -> str:
        return reverse("circles:event_detail", kwargs={"event_slug": self.slug})

    def seats_left(self):
        return self.seats - self.attendees.count()

    def attendee_list(self):
        return ", ".join([str(attendee) for attendee in self.attendees.all()])

    def can_attend(self, silent=False):
        try:
            if not self.open:
                raise CircleEventException("Circle is not open")
            if self.cancelled:
                raise CircleEventException("Circle is cancelled")
            if self.started():
                raise CircleEventException("Circle has already started")
            if self.seats_left() <= 0:
                raise CircleEventException("No seats left")
            return True
        except CircleEventException as e:
            if silent:
                return False
            raise e

    def state(self, user: "User|None" = None):
        if self.cancelled:
            return CircleEventState.CANCELLED
        if self.started():
            return CircleEventState.CLOSED
        if self.open:
            return CircleEventState.OPEN
        if user is not None and user in self.attendees.all():
            return CircleEventState.JOINABLE
        return CircleEventState.CLOSED

    def add_attendee(self, user):
        if user.is_staff or self.can_attend():
            self.attendees.add(user)
            self.save()

    def started(self):
        return self.start < timezone.now()

    def end(self):
        return self.start + datetime.timedelta(minutes=self.duration_minutes)

    def can_join(self, user):
        now = timezone.now()
        grace_before = datetime.timedelta(minutes=30)
        grace_after = datetime.timedelta(minutes=10)
        grace_duration = datetime.timedelta(minutes=self.duration_minutes)
        if user not in self.attendees.all():
            return False
        if user in self.joined.all():
            # Come back any time if already joined.
            return self.start - grace_before < now < self.start + grace_duration
        return self.start - grace_before < now < self.start + grace_after

    def ended(self):
        return self.start + datetime.timedelta(minutes=self.duration_minutes) < timezone.now()

    def remove_attendee(self, user):
        if user not in self.attendees.all():
            return
        if self.cancelled:
            raise CircleEventException("Circle is cancelled")
        if self.started():
            raise CircleEventException("Circle has already started")
        self.attendees.remove(user)
        self.save()

    def notify(self, force=False):
        # Notify users who are attending that the circle is about to start
        if force is False and self.notified:
            return
        self.notified = True
        self.save()
        for user in self.attendees.all():
            send_notify_circle_starting(self, user)

    def advertise(self, force=False):
        # Notify users who are subscribed that a new event is available, if they aren't already attending.
        if force is False and self.advertised:
            return
        self.advertised = True
        self.save()
        for user in self.circle.subscribed.all():
            if self.can_attend(silent=True) and user not in self.attendees.all():
                send_notify_circle_advertisement(self, user)

    def cal_link(self):
        return full_url(self.get_absolute_url())

    def save(self, *args, **kwargs):
        if settings.SAVE_TO_GOOGLE_CALENDAR:
            calendar.save_event(
                event_id=self.slug,
                start=self.start.isoformat(),
                end=self.end().isoformat(),
                summary=self.circle.title,
                description=markdown.markdown(self.circle.content),
            )
        super().save(*args, **kwargs)

    def __str__(self):
        return f"CircleEvent: {self.start}"


class CircleEventException(Exception):
    pass
