from __future__ import annotations

from enum import Enum
from typing import List

from pydantic import BaseModel

import totem.circles.models as circle_models
from totem.notifications.utils import notify_users
from totem.users.models import User


class NotificationType(str, Enum):
    CIRCLE_STARTING = "circle_starting"
    CIRCLE_ADVERTISEMENT = "circle_advertisement"
    CIRCLE_SIGNUP = "circle_signup"
    MISSED_EVENT = "missed_event"


class Notification(BaseModel):
    recipients: List[User]
    title: str
    message: str
    category: str
    extra_data: dict = {}

    class Config:
        arbitrary_types_allowed = True

    def send(self):
        """
        Sends the notification to the user and logs the event.
        """
        notify_users(
            users=self.recipients,
            title=self.title,
            body=self.message,
            data={
                "type": self.category,
                **self.extra_data,
            },
        )


class CircleStartingNotification(Notification):
    category: str = NotificationType.CIRCLE_STARTING


class CircleAdvertisementNotification(Notification):
    category: str = NotificationType.CIRCLE_ADVERTISEMENT


class MissedEventNotification(Notification):
    category: str = NotificationType.MISSED_EVENT


def circle_starting_notification(event: circle_models.CircleEvent, user: User) -> Notification:
    """Creates a notification that a Circle is starting soon."""
    return CircleStartingNotification(
        recipients=[user],
        title="🚨 Your Space is starting soon!",
        message=event.circle.title,
        extra_data={
            "event_slug": event.slug,
        },
    )


def circle_advertisement_notification(event: circle_models.CircleEvent, user: User) -> Notification:
    """Creates a notification to advertise a new Circle event."""
    title = event.title or event.circle.subtitle
    author_name = event.circle.author.name
    image_url = event.circle.image.url if event.circle.image else None

    return CircleAdvertisementNotification(
        recipients=[user],
        title=f"New Space Available: {title}",
        message=f"A new session by {author_name} has been posted. Reserve a spot now!",
        extra_data={
            "event_slug": event.slug,
            "image_url": image_url,
        },
    )


def missed_event_notification(event: circle_models.CircleEvent, user: User) -> Notification:
    """Creates a notification for a user who missed an event."""
    title = event.title or event.circle.title
    return MissedEventNotification(
        recipients=[user],
        title="We missed you!",
        message=f"We missed you at the {title} session.",
        extra_data={
            "event_slug": event.slug,
        },
    )
