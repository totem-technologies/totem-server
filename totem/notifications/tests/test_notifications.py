from collections.abc import Callable
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from totem.notifications.models import FCMDevice
from totem.notifications.notifications import (
    Notification,
    missed_session_notification,
    session_advertisement_notification,
    session_starting_notification,
)
from totem.notifications.schemas import NotificationType, SessionNotificationPayload
from totem.spaces.models import Session
from totem.spaces.tests.factories import SessionFactory, SpaceFactory
from totem.users.models import User
from totem.users.tests.factories import UserFactory


@pytest.mark.parametrize(
    ("builder", "kind", "title", "message"),
    [
        (
            session_starting_notification,
            "session_starting",
            "🚨 Your Space is starting soon!",
            "Space title",
        ),
        (
            session_advertisement_notification,
            "session_advertisement",
            "New Space Available: Session title",
            "A new session by Author has been posted. Reserve a spot now!",
        ),
        (
            missed_session_notification,
            "missed_session",
            "We missed you!",
            "We missed you at the Session title session.",
        ),
    ],
)
def test_session_notification_payload_and_delivery(
    builder: Callable[[Session, User], Notification],
    kind: str,
    title: str,
    message: str,
) -> None:
    user = UserFactory.build()
    space = SpaceFactory.build(title="Space title", slug="space_slug", author__name="Author")
    session = SessionFactory.build(space=space, title="Session title", slug="session-slug")

    notification = builder(session, user)

    assert isinstance(notification.payload, SessionNotificationPayload)
    with patch("totem.notifications.notifications.notify_users") as send:
        notification.send()
    send.assert_called_once_with(
        users=[user],
        title=title,
        body=message,
        data=SessionNotificationPayload(
            type=NotificationType(kind), space_slug="space_slug", session_slug="session-slug"
        ),
    )


@pytest.mark.parametrize("kind", ["circle_starting", "circle_advertisement", "circle_signup", "missed_event"])
def test_payload_rejects_legacy_types(kind: str) -> None:
    with pytest.raises(ValidationError):
        SessionNotificationPayload.model_validate({"type": kind, "space_slug": "space", "session_slug": "session"})


def test_payload_preserves_valid_short_and_long_slugs() -> None:
    payload = SessionNotificationPayload(type=NotificationType.SESSION_STARTING, space_slug="a", session_slug="a" * 50)
    assert payload.space_slug == "a"
    assert payload.session_slug == "a" * 50


@pytest.mark.parametrize("slug", ["", "a" * 51, "a b", "é", "slug\n"])
@pytest.mark.parametrize("field", ["space_slug", "session_slug"])
def test_payload_rejects_invalid_slugs(field: str, slug: str) -> None:
    data = {"space_slug": "space", "session_slug": "session", field: slug}
    with pytest.raises(ValidationError):
        SessionNotificationPayload(type=NotificationType.SESSION_STARTING, **data)


@pytest.mark.django_db
def test_session_notification_reaches_firebase() -> None:
    user = UserFactory()
    FCMDevice.objects.create(user=user, fid="installation-id")
    space = SpaceFactory.build(title="Space title", slug="space-slug")
    session = SessionFactory.build(space=space, slug="session-slug")

    with (
        patch("totem.notifications.services.initialize_firebase", return_value=True),
        patch("totem.notifications.services.messaging.send") as send,
    ):
        session_starting_notification(session, user).send()

    send.assert_called_once()
    message = send.call_args.args[0]
    assert message.fid == "installation-id"
    assert message.data == {"type": "session_starting", "space_slug": "space-slug", "session_slug": "session-slug"}
    assert message.notification.title == "🚨 Your Space is starting soon!"
    assert message.notification.body == "Space title"


def test_advertisement_uses_fallback_title_without_image_payload() -> None:
    space = SpaceFactory.build(subtitle="Fallback", image="spaces/image.jpg")
    session = SessionFactory.build(space=space, title="")
    notification = session_advertisement_notification(session, UserFactory.build())

    assert notification.title == "New Space Available: Fallback"
    assert "image_url" not in notification.payload.model_dump()
