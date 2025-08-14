from __future__ import annotations

import datetime
import time
from enum import Enum
from typing import TYPE_CHECKING

import pytz
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

from totem.utils.hash import basic_hash
from totem.utils.md import MarkdownField, MarkdownMixin
from totem.utils.models import AdminURLMixin, SluggedModel

if TYPE_CHECKING:
    from totem.users.models import User


class SeriesEventState(Enum):
    """Defines the possible states of a SeriesEvent."""

    OPEN = "OPEN"
    CLOSED = "CLOSED"
    JOINABLE = "JOINABLE"
    ENDED = "ENDED"
    STARTED = "STARTED"
    CANCELLED = "CANCELLED"


class SeriesImageSpec(ImageSpec):
    """Defines the image processing for Series images."""

    processors = [ResizeToFit(1500, 1500)]
    format = "JPEG"
    options = {"quality": 80, "optimize": True}


def upload_to_series_image(instance: Series, filename: str) -> str:
    """Generates a unique upload path for a Series image."""
    extension = filename.split(".")[-1]
    epoch_time = int(time.time())
    new_filename = basic_hash(f"{instance.slug}-{filename}-{epoch_time}")
    author_slug = instance.author.slug
    return f"series/{author_slug}/{new_filename}.{extension}"


class SeriesCategory(models.Model):
    """A category for organizing Series."""

    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    description = models.CharField(max_length=2000, blank=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Series Category"
        verbose_name_plural = "Series Categories"


class Series(AdminURLMixin, MarkdownMixin, SluggedModel):
    """
    A Series is a collection of events that are thematically linked
    and intended to be experienced as a sequence.
    """

    title = models.CharField(max_length=255)
    subtitle = models.CharField(max_length=2000)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        limit_choices_to={"is_staff": True},
        related_name="created_series",
    )
    categories = models.ManyToManyField(SeriesCategory, blank=True)
    image = ProcessedImageField(
        blank=True,
        null=True,
        upload_to=upload_to_series_image,
        spec=SeriesImageSpec,  # type: ignore
        help_text="Image for the Series header, must be under 5mb.",
    )
    tags = TaggableManager(blank=True)
    short_description = models.CharField(max_length=255, blank=True, help_text="Short description, max 255 characters.")
    content = MarkdownField(default="", help_text="Detailed description of the series.")
    published = models.BooleanField(default=False, help_text="Make this series visible to users.")
    subscribers = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="subscribed_series")
    events: QuerySet[SeriesEvent]

    def __str__(self):
        return self.title

    def get_absolute_url(self) -> str:
        return reverse("series:detail", kwargs={"slug": self.slug})

    def next_event(self):
        return self.events.filter(start__gte=timezone.now()).order_by("start").first()


class SeriesEvent(AdminURLMixin, MarkdownMixin, SluggedModel):
    """An individual event session within a Series."""

    series = models.ForeignKey(Series, on_delete=models.CASCADE, related_name="events")
    title = models.CharField(max_length=255, blank=True)
    start = models.DateTimeField(default=timezone.now)
    duration_minutes = models.IntegerField(_("Minutes"), default=60)
    attendees = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="events_attending_series")
    order = models.PositiveIntegerField(default=1, help_text="The sequence number of this event within the series.")
    published = models.BooleanField(default=False, help_text="Make this event visible.")
    cancelled = models.BooleanField(default=False, help_text="Mark this event as cancelled.")
    meeting_url = models.CharField(max_length=255, blank=True)

    class Meta:  # pyright: ignore [reportIncompatibleVariableOverride]
        ordering = ["series", "order", "start"]
        unique_together = [
            ["series", "start", "title"],
            ["series", "order"],
        ]
        verbose_name = "Series Event"
        verbose_name_plural = "Series Events"

    def __str__(self):
        return f'"{self.series.title}" Session {self.order}: "{self.title or "Event"}"'

    def get_absolute_url(self) -> str:
        return reverse("series:event_detail", kwargs={"series_slug": self.series.slug, "event_slug": self.slug})

    def end(self) -> datetime.datetime:
        return self.start + datetime.timedelta(minutes=self.duration_minutes)

    def has_started(self) -> bool:
        return self.start < timezone.now()

    def has_ended(self) -> bool:
        return self.end() < timezone.now()

    def event_title_or_series_title(self) -> str:
        return self.title or self.series.title
