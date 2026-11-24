from __future__ import annotations

from pydantic import BaseModel, ConfigDict

import totem.spaces.models as space_models
from totem.notifications.schemas import NotificationType, SessionNotificationPayload
from totem.notifications.utils import notify_users
from totem.users.models import User


class Notification(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    recipients: list[User]
    title: str
    message: str
    payload: SessionNotificationPayload

    def send(self) -> None:
        """
        Sends the notification to the user and logs the event.
        """
        notify_users(
            users=self.recipients,
            title=self.title,
            body=self.message,
            data=self.payload,
        )


def session_starting_notification(event: space_models.Session, user: User) -> Notification:
    """Creates a notification that a session is starting soon."""
    return Notification(
        recipients=[user],
        title="🚨 Your Space is starting soon!",
        message=event.space.title,
        payload=SessionNotificationPayload(
            type=NotificationType.SESSION_STARTING,
            space_slug=event.space.slug,
            session_slug=event.slug,
        ),
    )


def session_advertisement_notification(event: space_models.Session, user: User) -> Notification:
    """Creates a notification to advertise a new session."""
    title = event.title or event.space.subtitle
    author_name = event.space.author.name

    return Notification(
        recipients=[user],
        title=f"New Space Available: {title}",
        message=f"A new session by {author_name} has been posted. Reserve a spot now!",
        payload=SessionNotificationPayload(
            type=NotificationType.SESSION_ADVERTISEMENT,
            space_slug=event.space.slug,
            session_slug=event.slug,
        ),
    )


def missed_session_notification(event: space_models.Session, user: User) -> Notification:
    """Creates a notification for a user who missed a session."""
    title = event.title or event.space.title
    return Notification(
        recipients=[user],
        title="We missed you!",
        message=f"We missed you at the {title} session.",
        payload=SessionNotificationPayload(
            type=NotificationType.MISSED_SESSION,
            space_slug=event.space.slug,
            session_slug=event.slug,
        ),
    )
