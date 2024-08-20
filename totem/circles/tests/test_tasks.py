from datetime import timedelta

from django.core import mail
from django.utils import timezone

from totem.circles.tasks import notify_missed_event
from totem.circles.tests.factories import CircleEventFactory, CircleFactory
from totem.users.tests.factories import UserFactory


class TestMissedEventTask:
    def test_notify_missed_event_no_attending(self, db):
        event = CircleEventFactory()
        ended_event = CircleEventFactory(start=timezone.now() - timedelta(hours=1, minutes=30))
        event.save()
        assert event.notified_missed is False
        assert ended_event.notified_missed is False
        notify_missed_event()
        event.refresh_from_db()
        ended_event.refresh_from_db()
        assert event.notified_missed is False
        assert ended_event.notified_missed is True
        assert mail.outbox == []

    def test_notify_missed_event_attending(self, db):
        author = UserFactory()
        space = CircleFactory(author=author)
        event = CircleEventFactory(circle=space, start=timezone.now() - timedelta(hours=1, minutes=30))
        CircleEventFactory(start=timezone.now() - timedelta(hours=3))  # past event
        user = UserFactory()
        joined_user = UserFactory()
        event.attendees.add(user)
        event.attendees.add(joined_user)
        event.attendees.add(author)
        event.joined.add(joined_user)
        event.save()
        assert event.notified_missed is False
        assert notify_missed_event() == 1
        event.refresh_from_db()
        assert event.notified_missed is True
        assert len(mail.outbox) == 1
        email = mail.outbox[0]
        assert email.to == [user.email]
        message = str(email.message())
        assert "missed you" in message
        assert "forms.gle" in message
        assert notify_missed_event() == 0
