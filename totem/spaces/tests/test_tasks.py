from datetime import timedelta
from unittest.mock import patch

from django.core import mail
from django.utils import timezone

from totem.email.exceptions import EmailBounced
from totem.rooms.models import Room
from totem.spaces.models import Session, Space
from totem.spaces.tasks import notify_missed_session
from totem.spaces.tests.factories import SessionFactory, SpaceFactory
from totem.users.tests.factories import UserFactory
from totem.utils.testing import email_text


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

    def test_notify_missed_session_attending(self, db, django_capture_on_commit_callbacks):
        author = UserFactory()
        space = SpaceFactory(author=author)
        event = SessionFactory(space=space, start=timezone.now() - timedelta(hours=1, minutes=30))
        SessionFactory(start=timezone.now() - timedelta(hours=6))  # past event, outside the lookback
        user = UserFactory()
        joined_user = UserFactory()
        event.attendees.add(user)
        event.attendees.add(joined_user)
        event.attendees.add(author)
        event.joined.add(joined_user)
        event.save()
        assert event.notified_missed is False
        with django_capture_on_commit_callbacks(execute=True):
            assert notify_missed_session() == 1
        event.refresh_from_db()
        assert event.notified_missed is True
        assert len(mail.outbox) == 1
        email = mail.outbox[0]
        assert email.to == [user.email]
        message = email_text(email)
        assert "missed you" in message
        assert "forms.gle" in message
        with django_capture_on_commit_callbacks(execute=True):
            assert notify_missed_session() == 0

    @patch("totem.spaces.models.missed_session_email")
    def test_notify_missed_session_email_bounced(self, mock_email, db, django_capture_on_commit_callbacks):
        """A bounced email leaves the user's space subscription alone."""
        mock_email.return_value.send.side_effect = EmailBounced()
        author = UserFactory()
        space = SpaceFactory(author=author)
        event = SessionFactory(space=space, start=timezone.now() - timedelta(hours=1, minutes=30))
        user = UserFactory()
        event.attendees.add(user)
        space.subscribed.add(user)
        event.save()

        assert user in space.subscribed.all()
        with django_capture_on_commit_callbacks(execute=True):
            notify_missed_session()
        event.refresh_from_db()

        assert event.notified_missed is True
        assert user in space.subscribed.all()

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

    def test_notify_missed_session_long_duration_ended(self, db, django_capture_on_commit_callbacks):
        """A long-duration session that has ended should trigger notify_missed."""
        event = SessionFactory(
            start=timezone.now() - timedelta(hours=1, minutes=30),
            duration_minutes=60,
        )
        user = UserFactory()
        event.attendees.add(user)
        event.save()
        assert event.ended() is True
        with django_capture_on_commit_callbacks(execute=True):
            notify_missed_session()
        event.refresh_from_db()
        assert event.notified_missed is True
        assert len(mail.outbox) == 1

    def _overrunning_livekit_session(self, scheduled_end_ago: timedelta) -> Session:
        session = SessionFactory(
            space__meeting_provider=Space.MeetingProviderChoices.LIVEKIT,
            start=timezone.now() - scheduled_end_ago - timedelta(minutes=60),
            duration_minutes=60,
        )
        session.attendees.add(UserFactory())
        room = Room.objects.get_or_create_for_session(session)
        room.date_created = session.start
        room.save(update_fields=["date_created"])
        return session

    def test_notify_missed_session_skips_livekit_overrun(self, db):
        """A LiveKit room opened in time keeps the session live past its scheduled end."""
        session = self._overrunning_livekit_session(scheduled_end_ago=timedelta(minutes=30))
        assert session.ended() is False
        assert notify_missed_session() == 0
        session.refresh_from_db()
        assert session.notified_missed is False
        assert mail.outbox == []

    def test_notify_missed_session_livekit_ended_late(self, db, django_capture_on_commit_callbacks):
        """An overrunning LiveKit session is notified once ended_at is set, even
        if that's more than an hour past the scheduled end."""
        session = self._overrunning_livekit_session(scheduled_end_ago=timedelta(minutes=90))
        session.ended_at = timezone.now() - timedelta(minutes=5)
        session.save()
        with django_capture_on_commit_callbacks(execute=True):
            assert notify_missed_session() == 1
        session.refresh_from_db()
        assert session.notified_missed is True
        assert len(mail.outbox) == 1

    def test_notify_missed_session_livekit_backstop(self, db):
        """If ended_at is never set, the backstop still ends the session and notifies."""
        session = self._overrunning_livekit_session(scheduled_end_ago=timedelta(hours=3, minutes=10))
        assert session.ended() is True
        assert notify_missed_session() == 1
        session.refresh_from_db()
        assert session.notified_missed is True


class TestNotifyBounceHandling:
    @patch("totem.spaces.models.notify_session_starting")
    def test_notify_email_bounced(self, mock_email, db, django_capture_on_commit_callbacks):
        """A bounced 'starting soon' email leaves the user's spot and space subscription alone."""
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

        with django_capture_on_commit_callbacks(execute=True):
            event.notify(force=True)
        event.refresh_from_db()

        assert event.notified is True
        assert user in event.attendees.all()
        assert user in space.subscribed.all()

    @patch("totem.spaces.models.notify_session_tomorrow")
    def test_notify_tomorrow_email_bounced(self, mock_email, db, django_capture_on_commit_callbacks):
        """A bounced 'tomorrow' email leaves the user's spot and space subscription alone."""
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

        with django_capture_on_commit_callbacks(execute=True):
            event.notify_tomorrow(force=True)
        event.refresh_from_db()

        assert event.notified_tomorrow is True
        assert user in event.attendees.all()
        assert user in space.subscribed.all()

    @patch("totem.spaces.models.notify_session_signup")
    def test_add_attendee_email_bounced(self, mock_email, db, django_capture_on_commit_callbacks):
        """A bounced signup email leaves the user's spot and space subscription alone."""
        mock_email.return_value.send.side_effect = EmailBounced()
        author = UserFactory()
        space = SpaceFactory(author=author)
        event = SessionFactory(space=space, start=timezone.now() + timedelta(days=1))
        user = UserFactory()
        space.subscribed.add(user)

        assert user not in event.attendees.all()
        assert user in space.subscribed.all()

        with django_capture_on_commit_callbacks(execute=True):
            event.add_attendee(user)
        event.refresh_from_db()

        assert user in event.attendees.all()
        assert user in space.subscribed.all()
