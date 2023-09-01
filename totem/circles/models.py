import datetime

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from taggit.managers import TaggableManager

from totem.utils.md import MarkdownField, MarkdownMixin
from totem.utils.models import SluggedModel

# Create your models here.


class Circle(MarkdownMixin, SluggedModel):
    title = models.CharField(max_length=255)
    subtitle = models.CharField(max_length=2000)
    image = models.ImageField(upload_to="circles", blank=True, null=True)
    tags = TaggableManager()
    content = MarkdownField(default="")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, limit_choices_to={"is_staff": True})
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
    recurring = models.CharField(max_length=255)
    subscribed = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="subscribed_circles")

    def __str__(self):
        return self.title

    def get_absolute_url(self) -> str:
        return reverse("circles:detail", kwargs={"slug": self.slug})

    def subscribed_list(self):
        return ", ".join([str(attendee.email) for attendee in self.subscribed.all()])

    def next_event(self):
        return self.events.filter(start__gte=timezone.now()).order_by("start").first()

    def other_events(self):
        return self.events.filter(start__gte=timezone.now()).order_by("start")[:10]

    def is_free(self):
        return self.price == 0

    def subscribe(self, user):
        return self.subscribed.add(user)

    def unsubscribe(self, user):
        return self.subscribed.remove(user)


class CircleEvent(MarkdownMixin, SluggedModel):
    open = models.BooleanField(default=True, help_text="Is this Circle for more attendees?")
    cancelled = models.BooleanField(default=False, help_text="Is this Circle cancelled?")
    start = models.DateTimeField(default=timezone.now)
    duration_minutes = models.IntegerField(_("Minutes"), default=60)
    attendees = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="attending")
    seats = models.IntegerField(default=8)
    date_created = models.DateTimeField(auto_now_add=True)
    date_modified = models.DateTimeField(auto_now=True)
    circle = models.ForeignKey(Circle, on_delete=models.CASCADE, related_name="events")

    def get_absolute_url(self) -> str:
        return reverse("circles:event_detail", kwargs={"event_slug": self.slug, "slug": self.circle.slug})

    def seats_left(self):
        return self.seats - self.attendees.count()

    def attendee_list(self):
        return ", ".join([str(attendee) for attendee in self.attendees.all()])

    def add_attendee(self, user):
        if self.seats_left() <= 0:
            raise CircleEventException("No seats left")
        if user in self.attendees.all():
            return
        if not self.open and not user.is_staff:
            raise CircleEventException("Circle is not open")
        if self.cancelled:
            raise CircleEventException("Circle is cancelled")
        if self.started():
            raise CircleEventException("Circle has already started")
        self.attendees.add(user)
        self.save()

    def started(self):
        return self.start < timezone.now()

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

    def __str__(self):
        return f"<CircleEvent start: {self.start}>"


class CircleEventException(Exception):
    pass
