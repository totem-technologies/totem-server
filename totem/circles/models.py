import datetime
import time
from enum import Enum
from typing import TYPE_CHECKING

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

from totem.email.emails import (
    send_notify_circle_advertisement,
    send_notify_circle_signup,
    send_notify_circle_starting,
    send_notify_circle_tomorrow,
)
from totem.utils.hash import basic_hash, hmac
from totem.utils.md import MarkdownField, MarkdownMixin
from totem.utils.models import AdminURLMixin, SluggedModel
from totem.utils.slack import notify_slack
from totem.utils.utils import full_url

from .actions import JoinCircleAction, SubscribeAction
from .calendar import calendar

if TYPE_CHECKING:
    from totem.users.models import User

_default_grace_period = datetime.timedelta(minutes=10)


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


class CircleCategory(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    description = models.CharField(max_length=2000, blank=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "categories"


class Circle(AdminURLMixin, MarkdownMixin, SluggedModel):
    title = models.CharField(max_length=255)
    subtitle = models.CharField(max_length=2000)
    categories = models.ManyToManyField(CircleCategory, blank=True)
    image = ProcessedImageField(
        blank=True,
        null=True,
        upload_to=upload_to_id_image,
        spec=CircleImageSpec,  # type: ignore
        help_text="Image for the Space header, must be under 5mb",
    )
    tags = TaggableManager(blank=True)
    content = MarkdownField(default="")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        limit_choices_to={"is_staff": True},
        related_name="created_circles",
    )
    published = models.BooleanField(default=False, help_text="Is this listing visible?")
    open = models.BooleanField(default=True, help_text="Is this listing open for more attendees?")
    price = models.IntegerField(
        default=0,
        help_text="Price in USD dollars. If you want to offer this listing for free, enter 0.",
        verbose_name="Price (USD)",
        validators=[
            MinValueValidator(0, message="Price must be greater than or equal to 0"),
            MaxValueValidator(1000, message="Price must be less than or equal to 1000"),
        ],
    )
    recurring = models.CharField(
        max_length=255,
        help_text="Example: Once a month (or week, day, etc). Do not put specific times or days of the week.",
    )
    subscribed = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="subscribed_circles")
    events: QuerySet["CircleEvent"]

    def __str__(self):
        return self.title

    def get_absolute_url(self) -> str:
        return reverse("circles:detail", kwargs={"slug": self.slug})

    def subscribed_list(self):
        return ", ".join([str(attendee.email) for attendee in self.subscribed.all()])

    def next_event(self):
        return self.events.filter(start__gte=timezone.now() - _default_grace_period).order_by("start").first()

    def is_free(self):
        return self.price == 0

    def subscribe(self, user):
        return self.subscribed.add(user)

    def unsubscribe(self, user):
        return self.subscribed.remove(user)

    def subscribe_url(self, user, subscribe: bool) -> str:
        return SubscribeAction(user, parameters={"circle_slug": self.slug, "subscribe": subscribe}).build_url()


class CircleEvent(AdminURLMixin, MarkdownMixin, SluggedModel):
    listed = models.BooleanField(
        default=True,
        help_text="Is this session discoverable? False means events are only accessible via direct link, or to people attending.",
    )
    title = models.CharField(max_length=255, blank=True)
    advertised = models.BooleanField(default=False)
    attendees = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="events_attending")
    cancelled = models.BooleanField(default=False, help_text="Is this session cancelled?")
    circle = models.ForeignKey(Circle, on_delete=models.CASCADE, related_name="events")
    content = MarkdownField(
        help_text="Optional description for this specific session. Markdown is supported.",
        null=True,
        blank=True,
    )
    duration_minutes = models.IntegerField(_("Minutes"), default=60)
    joined = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="events_joined")
    meeting_url = models.CharField(max_length=255, blank=True)
    notified = models.BooleanField(default=False)
    notified_tomorrow = models.BooleanField(default=False)
    open = models.BooleanField(default=True, help_text="Is this session open for more attendees?")
    seats = models.IntegerField(default=8)
    start = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["start"]
        unique_together = [["circle", "start", "open", "title"]]

    def get_absolute_url(self) -> str:
        return reverse("circles:event_detail", kwargs={"event_slug": self.slug})

    def seats_left(self):
        return self.seats - self.attendees.count()

    def attendee_list(self):
        return ", ".join([str(attendee) for attendee in self.attendees.all()])

    def can_attend(self, user: "User | None" = None, silent=False):
        try:
            if user and user in self.attendees.all():
                raise CircleEventException("You are already attending this session")
            if user and user.is_staff:
                return True
            if not self.open:
                raise CircleEventException("Session is not available for signup")
            if self.cancelled:
                raise CircleEventException("Session was cancelled")
            if self.started():
                raise CircleEventException("Session has already started")
            if self.seats_left() <= 0:
                raise CircleEventException("There are no spots left")
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
        # checks if the user can attend and adds them to the attendees list, throws an exception if they can't
        if self.can_attend(user=user):
            self.attendees.add(user)
            if self.notified and self.can_join(user):
                # Send the user the join email if they are attending and the event is about to start
                send_notify_circle_starting(self, user)
            else:
                # Otherwise, send the user the signed up email
                send_notify_circle_signup(self, user)
            if not self.circle.author == user:
                notify_slack(
                    f"New session attendee: <{full_url(user.get_admin_url())}|{user.name}> for <{full_url(self.get_admin_url())}|{self.circle.title}> by {self.circle.author.name}"
                )

    def started(self):
        return self.start < timezone.now()

    def end(self):
        return self.start + datetime.timedelta(minutes=self.duration_minutes)

    def can_join(self, user):
        now = timezone.now()
        grace_before = datetime.timedelta(minutes=15)
        grace_after = _default_grace_period
        if user.is_staff or user in self.joined.all():
            # Come back any time if already joined.
            grace_before = datetime.timedelta(minutes=60)
            grace_after = datetime.timedelta(minutes=self.duration_minutes)
        if user not in self.attendees.all():
            return False
        return self.start - grace_before < now < self.start + grace_after

    def ended(self):
        return self.start + datetime.timedelta(minutes=self.duration_minutes) < timezone.now()

    def remove_attendee(self, user):
        if user not in self.attendees.all():
            return
        if self.cancelled:
            raise CircleEventException("Session is cancelled")
        if self.started():
            raise CircleEventException("Session has already started")
        self.attendees.remove(user)

    def notify(self, force=False):
        # Notify users who are attending that the circle is about to start
        if force is False and self.notified:
            return
        self.notified = True
        self.save()
        for user in self.attendees.all():
            send_notify_circle_starting(self, user)

    def notify_tomorrow(self, force=False):
        # Notify users who are attending that the circle is starting tomorrow
        if force is False and self.notified_tomorrow:
            return
        self.notified_tomorrow = True
        self.save()
        for user in self.attendees.all():
            send_notify_circle_tomorrow(self, user)

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

    def save_to_calendar(self):
        cal_event = calendar.save_event(
            event_id=self.slug,
            start=self.start.isoformat(),
            end=self.end().isoformat(),
            summary=self.circle.title,
            description=self.cal_link(),
        )
        if cal_event:
            self.meeting_url = cal_event.hangoutLink

    def delete(self, *args, **kwargs):
        calendar.delete_event(event_id=self.slug)
        super().delete(*args, **kwargs)

    def password(self):
        return basic_hash(hmac(f"{self.slug}|{self.meeting_url}"))

    def join_url(self, user):
        return JoinCircleAction(user=user, parameters={"event_slug": self.slug}).build_url()

    # def attend_url(self, user):
    #     return AttendCircleAction(user=user, parameters={"event_slug": self.slug}).build_url()

    def __str__(self):
        return f"CircleEvent: {self.start}"


class CircleEventException(Exception):
    pass
