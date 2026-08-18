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

from ..models import Session, SessionException, SessionTimeConflict
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

    def test_next_session_skips_unlisted_and_cancelled(self):
        space = SpaceFactory()
        unlisted = SessionFactory(space=space, start=timezone.now() + timezone.timedelta(days=1), listed=False)
        SessionFactory(space=space, start=timezone.now() + timezone.timedelta(days=2), cancelled=True)
        listed = SessionFactory(space=space, start=timezone.now() + timezone.timedelta(days=3))
        self.assertEqual(space.next_session(), listed)
        # Attendees keep access to their unlisted sessions.
        user = UserFactory()
        unlisted.attendees.add(user)
        self.assertEqual(space.next_session(user), unlisted)
        # But not to cancelled ones.
        self.assertEqual(space.next_session(UserFactory()), listed)

    def test_next_session_unpublished_space(self):
        space = SpaceFactory(published=False)
        session = SessionFactory(space=space, start=timezone.now() + timezone.timedelta(days=1))
        self.assertIsNone(space.next_session())
        self.assertIsNone(space.next_session(UserFactory()))
        self.assertEqual(space.next_session(UserFactory(is_staff=True)), session)


class TestSessionVisibleTo(TestCase):
    """SessionQuerySet.visible_to is the single visibility policy: not cancelled,
    published space (staff exempt), not banned-from, and listed unless attending."""

    def setUp(self):
        self.space = SpaceFactory(published=True)
        self.listed = SessionFactory(space=self.space)
        self.unlisted = SessionFactory(space=self.space, listed=False)
        self.cancelled = SessionFactory(space=self.space, cancelled=True)
        self.unpublished = SessionFactory(space=SpaceFactory(published=False))

    def _visible(self, user):
        return list(Session.objects.visible_to(user))

    def test_anonymous(self):
        self.assertEqual(self._visible(None), [self.listed])

    def test_authenticated(self):
        self.assertEqual(self._visible(UserFactory()), [self.listed])

    def test_attendee_sees_unlisted_but_not_cancelled(self):
        user = UserFactory()
        self.unlisted.attendees.add(user)
        self.cancelled.attendees.add(user)
        visible = self._visible(user)
        self.assertIn(self.unlisted, visible)
        self.assertNotIn(self.cancelled, visible)

    def test_staff_sees_unpublished_but_not_unlisted(self):
        visible = self._visible(UserFactory(is_staff=True))
        self.assertIn(self.unpublished, visible)
        self.assertNotIn(self.unlisted, visible)

    def test_banned_hidden(self):
        user = UserFactory()
        _ban_user(self.listed, user)
        self.assertEqual(self._visible(user), [])

    def test_attendee_no_duplicates(self):
        user = UserFactory()
        self.listed.attendees.add(user)
        self.assertEqual(self._visible(user), [self.listed])

    def test_unpublished_is_staff_only_even_for_attendees(self):
        # Unpublished is a pre-launch draft state, not a retirement state;
        # there is no attendee exception. Invite-only sessions use unlisted.
        user = UserFactory()
        self.unpublished.attendees.add(user)
        self.assertNotIn(self.unpublished, self._visible(user))


class TestSessionHistoryFor(TestCase):
    """history_for is the user's personal record: sessions they joined, newest
    first. Cancelled and unlisted sessions stay in it, and a site-wide ban
    doesn't scrub it. Unpublished spaces are staff-only drafts, so they drop
    out for everyone else."""

    def setUp(self):
        self.user = UserFactory()
        self.space = SpaceFactory(published=True)
        start = timezone.now() - timezone.timedelta(days=30)
        step = timezone.timedelta(days=1)
        self.listed = SessionFactory(space=self.space, start=start + 4 * step)
        self.unlisted = SessionFactory(space=self.space, start=start + 3 * step, listed=False)
        self.cancelled = SessionFactory(space=self.space, start=start + 2 * step, cancelled=True)
        self.banned_from = SessionFactory(space=self.space, start=start + step)
        for session in (self.listed, self.unlisted, self.cancelled, self.banned_from):
            session.joined.add(self.user)
        _ban_user(self.banned_from, self.user)
        # Attended but never joined: not part of the record.
        self.not_joined = SessionFactory(space=self.space, start=start)
        self.not_joined.attendees.add(self.user)

    def test_personal_record_newest_first(self):
        history = list(Session.objects.history_for(self.user))
        self.assertEqual(history, [self.listed, self.unlisted, self.cancelled, self.banned_from])

    def test_unpublished_is_staff_only(self):
        staff = UserFactory(is_staff=True)
        draft = SessionFactory(space=SpaceFactory(published=False), start=timezone.now() - timezone.timedelta(days=1))
        draft.joined.add(self.user, staff)
        self.assertNotIn(draft, Session.objects.history_for(self.user))
        self.assertIn(draft, Session.objects.history_for(staff))


class TestCanView(TestCase):
    """can_view is the page/detail access rule: published, or staff. Unlisted
    and cancelled pages stay reachable by direct link."""

    def test_published(self):
        session = SessionFactory(listed=False, cancelled=True)
        self.assertTrue(session.can_view(None))
        self.assertTrue(session.can_view(UserFactory()))

    def test_unpublished(self):
        session = SessionFactory(space=SpaceFactory(published=False))
        self.assertFalse(session.can_view(None))
        user = UserFactory()
        session.attendees.add(user)
        session.joined.add(user)
        self.assertFalse(session.can_view(user))
        self.assertTrue(session.can_view(UserFactory(is_staff=True)))

    def test_everything_listed_is_viewable(self):
        # The structural invariant: any session a listing or history policy
        # returns for a user must be openable by that same user.
        published = SpaceFactory(published=True)
        unpublished = SpaceFactory(published=False)
        attendee = UserFactory()
        staff = UserFactory(is_staff=True)
        start = timezone.now() - timezone.timedelta(days=10)
        for space in (published, unpublished):
            for listed in (True, False):
                for cancelled in (True, False):
                    start += timezone.timedelta(hours=1)
                    session = SessionFactory(space=space, listed=listed, cancelled=cancelled, start=start)
                    session.attendees.add(attendee)
                    session.joined.add(attendee, staff)
        for viewer in (None, attendee, staff):
            for session in Session.objects.visible_to(viewer):
                self.assertTrue(session.can_view(viewer))
        for viewer in (attendee, staff):
            for session in Session.objects.history_for(viewer):
                self.assertTrue(session.can_view(viewer))


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

    def test_duration_capped_at_two_hours(self, db):
        session = SessionFactory(duration_minutes=121)
        with pytest.raises(ValidationError):
            session.full_clean()
        session.duration_minutes = 120
        session.full_clean()  # should not raise

    def test_duration_cannot_be_zero(self, db):
        session = SessionFactory(duration_minutes=0)
        with pytest.raises(ValidationError):
            session.full_clean()

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

    def test_can_attend_unpublished_draft(self, db):
        # Drafts are staff-only; nobody else can sign up, even with the slug.
        session = SessionFactory(space__published=False)
        with pytest.raises(SessionException):
            session.can_attend(user=UserFactory())
        assert session.can_attend(user=UserFactory(is_staff=True))

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

    def test_can_attend_rejects_overlapping_session(self, db):
        user = UserFactory()
        start = timezone.now() + timezone.timedelta(days=1)
        attending = SessionFactory(start=start, duration_minutes=60)
        attending.attendees.add(user)
        session = SessionFactory(start=start + timezone.timedelta(minutes=30), duration_minutes=60)

        with pytest.raises(SessionTimeConflict) as exc_info:
            session.can_attend(user=user)

        assert exc_info.value.conflicting_session == attending

    def test_can_attend_staff_allows_overlapping_session(self, db):
        staff = UserFactory(is_staff=True)
        start = timezone.now() + timezone.timedelta(days=1)
        attending = SessionFactory(start=start, duration_minutes=60)
        attending.attendees.add(staff)
        session = SessionFactory(start=start + timezone.timedelta(minutes=30), duration_minutes=60)

        assert session.can_attend(user=staff) is True

    def test_can_attend_ignores_session_in_unpublished_space(self, db):
        user = UserFactory()
        start = timezone.now() + timezone.timedelta(days=1)
        draft = SessionFactory(space__published=False, start=start, duration_minutes=60)
        draft.attendees.add(user)
        session = SessionFactory(start=start + timezone.timedelta(minutes=30), duration_minutes=60)

        assert session.can_attend(user=user) is True

    def test_can_attend_ignores_started_overlapping_session(self, db):
        user = UserFactory()
        attending = SessionFactory(
            start=timezone.now() - timezone.timedelta(minutes=30),
            duration_minutes=60,
        )
        attending.attendees.add(user)
        session = SessionFactory(start=timezone.now() + timezone.timedelta(minutes=10), duration_minutes=60)

        assert session.can_attend(user=user) is True

    def test_can_attend_allows_back_to_back_session(self, db):
        user = UserFactory()
        start = timezone.now() + timezone.timedelta(days=1)
        attending = SessionFactory(start=start, duration_minutes=60)
        attending.attendees.add(user)
        session = SessionFactory(start=start + timezone.timedelta(minutes=60), duration_minutes=60)

        assert session.can_attend(user=user) is True

    def test_cancelled_session_does_not_conflict(self, db):
        user = UserFactory()
        start = timezone.now() + timezone.timedelta(days=1)
        attending = SessionFactory(start=start, duration_minutes=60, cancelled=True)
        attending.attendees.add(user)
        session = SessionFactory(start=start + timezone.timedelta(minutes=30), duration_minutes=60)

        assert session.can_attend(user=user) is True

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
