import io

import pytest
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from PIL import Image, ImageOps

from totem.users.tests.factories import UserFactory

from ..views import ics_hash
from .factories import SessionFactory, SpaceFactory


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


class TestSessionModel:
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
        message = str(email.message())
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
        message = str(email.message())
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
        message = str(email.message())
        assert "http://testserver/spaces/session" in message
        session.refresh_from_db()
        assert session.notified_tomorrow

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
