import io

import pytest
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone
from PIL import Image, ImageOps

from totem.rooms.models import Room
from totem.users.models import User
from totem.users.tests.factories import UserFactory
from totem.utils.testing import email_text

from ..models import Session
from ..views import ics_hash
from .factories import SessionFactory, SpaceFactory


def _ban_user(session: Session, user: User) -> None:
    room = Room.objects.get_or_create_for_session(session)
    room.banned_participants = [user.slug]
    room.save()


def test_ics_hash():
    slug = "my-slug"
    user_ics_key = 123456
    expected_hash = "e35dadad16952b194afc"
    assert ics_hash(slug, user_ics_key) == expected_hash


@pytest.mark.django_db
def test_space_image_bakes_in_exif_orientation():
    """A Space image with EXIF orientation should be physically rotated on save."""
    img = Image.new("RGB", (100, 100))
    img.paste((255, 0, 0), (0, 0, 50, 50))  # top-left: red
    img.paste((0, 255, 0), (50, 0, 100, 50))
    img.paste((0, 0, 255), (0, 50, 50, 100))
    img.paste((255, 255, 0), (50, 50, 100, 100))
    exif = Image.Exif()
    exif[0x0112] = 6  # rotate 90° clockwise to display
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif)
    raw = buf.getvalue()

    expected = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB")

    space = SpaceFactory()
    space.image.save("cover.jpg", SimpleUploadedFile("cover.jpg", raw, "image/jpeg"))
    space.refresh_from_db()

    with space.image.open("rb") as fh:
        processed = Image.open(fh).convert("RGB").resize((100, 100))

    def dominant(image, x, y):
        r, g, b = image.getpixel((x, y))[:3]
        return (255 if r > 128 else 0, 255 if g > 128 else 0, 255 if b > 128 else 0)

    assert dominant(processed, 25, 25) == dominant(expected, 25, 25)
    assert dominant(processed, 25, 25) != (255, 0, 0)


class SpaceModelTest(TestCase):
    def test_title_label(self):
        space = SpaceFactory()
        field_label = space._meta.get_field("title").verbose_name  # type: ignore
        self.assertEqual(field_label, "title")

    def test_get_absolute_url(self):
        space = SpaceFactory()
        # This will also fail if the urlconf is not defined.
        self.assertEqual(space.get_absolute_url(), f"/spaces/{space.slug}/")

    def test_subscribed_list(self):
        space = SpaceFactory()
        self.assertEqual(space.subscribed_list(), "")

    def test_price_min_value(self):
        space = SpaceFactory()
        space.price = -1
        with self.assertRaisesMessage(ValidationError, "Price must be greater than or equal to 0"):
            space.full_clean()

    def test_price_max_value(self):
        space = SpaceFactory()
        space.price = 1001
        with self.assertRaisesMessage(ValidationError, "Price must be less than or equal to 1000"):
            space.full_clean()

    def test_subscribed(self):
        space = SpaceFactory()
        self.assertEqual(space.subscribed.count(), 0)
        user = UserFactory()
        space.subscribed.add(user)
        self.assertEqual(space.subscribed.count(), 1)
        space.subscribed.add(user)
        self.assertEqual(space.subscribed.count(), 1)
        space.subscribed.remove(user)
        self.assertEqual(space.subscribed.count(), 0)

    def test_next_session_excludes_banned(self):
        user = UserFactory()
        space = SpaceFactory()
        first = SessionFactory(space=space, start=timezone.now() + timezone.timedelta(days=1))
        second = SessionFactory(space=space, start=timezone.now() + timezone.timedelta(days=2))
        _ban_user(first, user)
        self.assertEqual(space.next_session(), first)
        self.assertEqual(space.next_session(user), second)

    def test_next_session_in_progress_until_ended(self):
        # An in-progress session is still the next session so attendees can find it.
        space = SpaceFactory()
        in_progress = SessionFactory(
            space=space, start=timezone.now() - timezone.timedelta(minutes=30), duration_minutes=60
        )
        future = SessionFactory(space=space, start=timezone.now() + timezone.timedelta(days=1))
        self.assertEqual(space.next_session(), in_progress)

        in_progress.ended_at = timezone.now()
        in_progress.save()
        self.assertEqual(space.next_session(), future)

    def test_next_session_skips_ended(self):
        space = SpaceFactory()
        SessionFactory(space=space, start=timezone.now() - timezone.timedelta(hours=2), duration_minutes=60)
        future = SessionFactory(space=space, start=timezone.now() + timezone.timedelta(days=1))
        self.assertEqual(space.next_session(), future)


class TestSessionModel:
    def test_attendee_email_list(self, db):
        session = SessionFactory()
        assert session.attendee_email_list() == ""
        user1 = UserFactory()
        user2 = UserFactory()
        session.attendees.add(user1, user2)
        emails = session.attendee_email_list().split(", ")
        assert sorted(emails) == sorted([user1.email, user2.email])

    def test_seats_cannot_be_zero(self, db):
        session = SessionFactory(seats=0)
        with pytest.raises(ValidationError):
            session.full_clean()

    def test_seats_cannot_be_negative(self, db):
        session = SessionFactory(seats=-5)
        with pytest.raises(ValidationError):
            session.full_clean()

    def test_seats_minimum_is_one(self, db):
        session = SessionFactory(seats=1)
        session.full_clean()  # should not raise

    def test_notify(self, db):
        user = UserFactory()
        session = SessionFactory()
        session.attendees.add(user)
        assert mail.outbox == []
        session.save()
        assert not session.notified
        session.notify()
        assert len(mail.outbox) == 1
        email = mail.outbox[0]
        assert email.to == [user.email]
        message = email_text(email)
        assert "http://testserver/spaces/join/" in message
        session.refresh_from_db()
        assert session.notified

    def test_advertise(self, db):
        user = UserFactory()
        session = SessionFactory()
        session.space.subscribed.add(user)
        assert mail.outbox == []
        session.save()
        assert not session.advertised
        session.advertise()
        assert len(mail.outbox) == 1
        email = mail.outbox[0]
        assert email.to == [user.email]
        message = email_text(email)
        assert "http://testserver/spaces/session" in message
        assert "http://testserver/spaces/subscribe" in message
        session.refresh_from_db()
        assert session.advertised

    def test_notify_tomorrow(self, db):
        user = UserFactory()
        session = SessionFactory()
        session.attendees.add(user)
        assert mail.outbox == []
        session.save()
        assert not session.notified_tomorrow
        session.notify_tomorrow()
        assert len(mail.outbox) == 1
        email = mail.outbox[0]
        assert email.to == [user.email]
        message = email_text(email)
        assert "http://testserver/spaces/session" in message
        session.refresh_from_db()
        assert session.notified_tomorrow

    def test_notify_skips_banned(self, db):
        user = UserFactory()
        banned = UserFactory()
        session = SessionFactory()
        session.attendees.add(user, banned)
        _ban_user(session, banned)
        session.notify()
        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == [user.email]

    def test_notify_tomorrow_skips_banned(self, db):
        user = UserFactory()
        banned = UserFactory()
        session = SessionFactory()
        session.attendees.add(user, banned)
        _ban_user(session, banned)
        session.notify_tomorrow()
        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == [user.email]

    def test_notify_missed_skips_banned(self, db):
        user = UserFactory()
        banned = UserFactory()
        session = SessionFactory(start=timezone.now() - timezone.timedelta(hours=3))
        session.attendees.add(user, banned)
        _ban_user(session, banned)
        session.notify_missed()
        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == [user.email]

    def test_can_attend_banned(self, db):
        from ..models import SessionException

        user = UserFactory()
        session = SessionFactory()
        _ban_user(session, user)
        assert session.can_attend(user=user, silent=True) is False
        with pytest.raises(SessionException):
            session.can_attend(user=user)
        with pytest.raises(SessionException):
            session.add_attendee(user)
        assert user not in session.attendees.all()

    def test_join_window(self, db):
        from ..models import Space

        user = UserFactory()
        staff = UserFactory(is_staff=True)
        session = SessionFactory(start=timezone.now() + timezone.timedelta(days=1), duration_minutes=60)
        session.attendees.add(user, staff)

        opens, closes = session.join_window(user)
        assert opens == session.start - timezone.timedelta(minutes=15)
        assert closes == session.start + timezone.timedelta(minutes=10)

        opens, closes = session.join_window(staff)
        assert opens == session.start - timezone.timedelta(minutes=60)
        assert closes == session.start + timezone.timedelta(minutes=60)

        # Once someone has joined, they get the wide window so they can rejoin.
        session.joined.add(user)
        opens, closes = session.join_window(user)
        assert opens == session.start - timezone.timedelta(minutes=60)
        assert closes == session.start + timezone.timedelta(minutes=60)

        # LiveKit rooms stay open for rejoiners until explicitly ended.
        session.space.meeting_provider = Space.MeetingProviderChoices.LIVEKIT
        session.space.save()
        opens, closes = session.join_window(user)
        assert closes is None

    def test_can_join_matches_join_window(self, db):
        user = UserFactory()
        session = SessionFactory(start=timezone.now() + timezone.timedelta(minutes=5), duration_minutes=60)
        session.attendees.add(user)
        assert session.can_join(user) is True

        early = SessionFactory(start=timezone.now() + timezone.timedelta(minutes=20), duration_minutes=60)
        early.attendees.add(user)
        assert early.can_join(user) is False

        late = SessionFactory(start=timezone.now() - timezone.timedelta(minutes=11), duration_minutes=60)
        late.attendees.add(user)
        assert late.can_join(user) is False

    def test_ended_is_provider_aware(self, db):
        from ..models import Space

        # Google Meet gives no end signal; the scheduled end is the best guess.
        meet = SessionFactory(start=timezone.now() - timezone.timedelta(hours=2), duration_minutes=60)
        assert meet.ended() is True

        # LiveKit rooms end when the keeper ends them (ended_at), so an
        # overrunning session is still live.
        livekit = SessionFactory(start=timezone.now() - timezone.timedelta(hours=2), duration_minutes=60)
        livekit.space.meeting_provider = Space.MeetingProviderChoices.LIVEKIT
        livekit.space.save()
        assert livekit.ended() is False
        livekit.ended_at = timezone.now()
        assert livekit.ended() is True

        # Backstop: if the disconnect watchdog never fired, don't stay live forever.
        stale = SessionFactory(start=timezone.now() - timezone.timedelta(hours=5), duration_minutes=60)
        stale.space.meeting_provider = Space.MeetingProviderChoices.LIVEKIT
        stale.space.save()
        assert stale.ended() is True

    def test_can_attend_after_start(self, db):
        from ..models import SessionException

        user = UserFactory()
        session = SessionFactory(start=timezone.now() - timezone.timedelta(minutes=1))
        assert session.can_attend(user=user, silent=True) is False
        with pytest.raises(SessionException, match="already started"):
            session.can_attend(user=user)

    def test_advertise_skips_banned(self, db):
        user = UserFactory()
        banned = UserFactory()
        session = SessionFactory()
        session.space.subscribed.add(user, banned)
        _ban_user(session, banned)
        session.advertise()
        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == [user.email]

    def test_join_url_livekit(self, db):
        from ..models import Space

        space = SpaceFactory(meeting_provider=Space.MeetingProviderChoices.LIVEKIT)
        session = SessionFactory(space=space)
        url = session.room_url()
        assert f"/room/{session.slug}" in url

    def test_join_url_google_meet(self, db):
        from ..models import Space

        meeting_url = "https://example.com"
        space = SpaceFactory(meeting_provider=Space.MeetingProviderChoices.GOOGLE_MEET)
        session = SessionFactory(space=space, meeting_url=meeting_url)
        assert session.room_url() == meeting_url
