from datetime import timedelta
from unittest.mock import patch

from django.core import mail
from django.utils import timezone

from totem.email.exceptions import EmailBounced
from totem.spaces.tasks import notify_missed_session
from totem.spaces.tests.factories import SessionFactory, SpaceFactory
from totem.users.tests.factories import UserFactory


class TestMissedSessionTask:
    def test_notify_missed_session_no_attending(self, db):
        event = SessionFactory()
        ended_event = SessionFactory(start=timezone.now() - timedelta(hours=1, minutes=30))
        event.save()
        assert event.notified_missed is False
        assert ended_event.notified_missed is False
        notify_missed_session()
        event.refresh_from_db()
        ended_event.refresh_from_db()
        assert event.notified_missed is False
        assert ended_event.notified_missed is True
        assert mail.outbox == []

    def test_notify_missed_session_attending(self, db):
        author = UserFactory()
        space = SpaceFactory(author=author)
        event = SessionFactory(space=space, start=timezone.now() - timedelta(hours=1, minutes=30))
        SessionFactory(start=timezone.now() - timedelta(hours=3))  # past event
        user = UserFactory()
        joined_user = UserFactory()
        event.attendees.add(user)
        event.attendees.add(joined_user)
        event.attendees.add(author)
        event.joined.add(joined_user)
        event.save()
        assert event.notified_missed is False
        assert notify_missed_session() == 1
        event.refresh_from_db()
        assert event.notified_missed is True
        assert len(mail.outbox) == 1
        email = mail.outbox[0]
        assert email.to == [user.email]
        message = str(email.message())
        assert "missed you" in message
        assert "forms.gle" in message
        assert notify_missed_session() == 0

    @patch("totem.spaces.models.missed_session_email")
    def test_notify_missed_session_email_bounced(self, mock_email, db):
        """Test that a bounced email unsubscribes the user from the space."""
        mock_email.return_value.send.side_effect = EmailBounced()
        author = UserFactory()
        space = SpaceFactory(author=author)
        event = SessionFactory(space=space, start=timezone.now() - timedelta(hours=1, minutes=30))
        user = UserFactory()
        event.attendees.add(user)
        space.subscribed.add(user)
        event.save()

        assert user in space.subscribed.all()
        notify_missed_session()
        event.refresh_from_db()

        assert event.notified_missed is True
        assert user not in space.subscribed.all()

    def test_notify_missed_session_long_duration_not_ended(self, db):
        """A session that started 1.5h ago but has a 2h duration should NOT
        trigger notify_missed, because it hasn't actually ended yet."""
        event = SessionFactory(
            start=timezone.now() - timedelta(hours=1, minutes=30),
            duration_minutes=120,
        )
        user = UserFactory()
        event.attendees.add(user)
        event.save()
        assert event.ended() is False
        notify_missed_session()
        event.refresh_from_db()
        assert event.notified_missed is False
        assert mail.outbox == []

    def test_notify_missed_session_long_duration_ended(self, db):
        """A session that started 1.5h ago with a short duration SHOULD
        trigger notify_missed, because it has ended."""
        event = SessionFactory(
            start=timezone.now() - timedelta(hours=1, minutes=30),
            duration_minutes=30,
        )
        user = UserFactory()
        event.attendees.add(user)
        event.save()
        assert event.ended() is True
        notify_missed_session()
        event.refresh_from_db()
        assert event.notified_missed is True
        assert len(mail.outbox) == 1


class TestNotifyBounceHandling:
    @patch("totem.spaces.models.notify_session_starting")
    def test_notify_email_bounced(self, mock_email, db):
        """Test that a bounced 'starting soon' email removes user from session and space."""
        mock_email.return_value.send.side_effect = EmailBounced()
        author = UserFactory()
        space = SpaceFactory(author=author)
        event = SessionFactory(space=space, start=timezone.now() + timedelta(minutes=5))
        user = UserFactory()
        event.attendees.add(user)
        space.subscribed.add(user)
        event.save()

        assert user in event.attendees.all()
        assert user in space.subscribed.all()

        event.notify(force=True)
        event.refresh_from_db()

        assert event.notified is True
        assert user not in event.attendees.all()
        assert user not in space.subscribed.all()

    @patch("totem.spaces.models.notify_session_tomorrow")
    def test_notify_tomorrow_email_bounced(self, mock_email, db):
        """Test that a bounced 'tomorrow' email removes user from session and space."""
        mock_email.return_value.send.side_effect = EmailBounced()
        author = UserFactory()
        space = SpaceFactory(author=author)
        event = SessionFactory(space=space, start=timezone.now() + timedelta(days=1))
        user = UserFactory()
        event.attendees.add(user)
        space.subscribed.add(user)
        event.save()

        assert user in event.attendees.all()
        assert user in space.subscribed.all()

        event.notify_tomorrow(force=True)
        event.refresh_from_db()

        assert event.notified_tomorrow is True
        assert user not in event.attendees.all()
        assert user not in space.subscribed.all()

    @patch("totem.spaces.models.notify_session_signup")
    def test_add_attendee_email_bounced(self, mock_email, db):
        """Test that a bounced signup email removes user from session and space."""
        mock_email.return_value.send.side_effect = EmailBounced()
        author = UserFactory()
        space = SpaceFactory(author=author)
        event = SessionFactory(space=space, start=timezone.now() + timedelta(days=1))
        user = UserFactory()
        space.subscribed.add(user)

        assert user not in event.attendees.all()
        assert user in space.subscribed.all()

        event.add_attendee(user)
        event.refresh_from_db()

        assert user not in event.attendees.all()
        assert user not in space.subscribed.all()
