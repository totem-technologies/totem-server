from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict

import totem.spaces.models as space_models
from totem.notifications.utils import notify_users
from totem.users.models import User


class NotificationType(str, Enum):
    SESSION_STARTING = "circle_starting"
    SESSION_ADVERTISEMENT = "circle_advertisement"
    SESSION_SIGNUP = "circle_signup"
    MISSED_SESSION = "missed_event"

    CIRCLE_STARTING = SESSION_STARTING
    CIRCLE_ADVERTISEMENT = SESSION_ADVERTISEMENT
    CIRCLE_SIGNUP = SESSION_SIGNUP
    MISSED_EVENT = MISSED_SESSION


class Notification(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    recipients: list[User]
    title: str
    message: str
    category: str
    extra_data: dict = {}

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


class SessionStartingNotification(Notification):
    category: str = NotificationType.SESSION_STARTING


class SessionAdvertisementNotification(Notification):
    category: str = NotificationType.SESSION_ADVERTISEMENT


class MissedSessionNotification(Notification):
    category: str = NotificationType.MISSED_SESSION


def session_starting_notification(event: space_models.Session, user: User) -> Notification:
    """Creates a notification that a session is starting soon."""
    return SessionStartingNotification(
        recipients=[user],
        title="🚨 Your Space is starting soon!",
        message=event.space.title,
        extra_data={
            "space_slug": event.space.slug,
            "session_slug": event.slug,
        },
    )


def session_advertisement_notification(event: space_models.Session, user: User) -> Notification:
    """Creates a notification to advertise a new session."""
    title = event.title or event.space.subtitle
    author_name = event.space.author.name
    image_url = event.space.image.url if event.space.image else None

    return SessionAdvertisementNotification(
        recipients=[user],
        title=f"New Space Available: {title}",
        message=f"A new session by {author_name} has been posted. Reserve a spot now!",
        extra_data={
            "space_slug": event.space.slug,
            "session_slug": event.slug,
            "image_url": image_url,
        },
    )


def missed_session_notification(event: space_models.Session, user: User) -> Notification:
    """Creates a notification for a user who missed a session."""
    title = event.title or event.space.title
    return MissedSessionNotification(
        recipients=[user],
        title="We missed you!",
        message=f"We missed you at the {title} session.",
        extra_data={
            "space_slug": event.space.slug,
            "session_slug": event.slug,
        },
    )


circle_starting_notification = session_starting_notification
circle_advertisement_notification = session_advertisement_notification
missed_event_notification = missed_session_notification
