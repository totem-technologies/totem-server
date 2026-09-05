import io
from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from PIL import Image, ImageOps

from totem.users.models import LoginPin, PinFailureReason, User
from totem.users.tests.factories import UserFactory


def test_user_get_absolute_url(user: User):
    assert user.get_absolute_url() == f"/users/u/{user.slug}/"


def _make_oriented_image(orientation: int) -> bytes:
    """Build a JPEG with four distinct colored quadrants and an EXIF orientation tag.

    The pixels are stored un-rotated; the EXIF orientation tag (0x0112) tells viewers
    how to display them. A correct uploader must bake that rotation into the pixels.
    """
    img = Image.new("RGB", (100, 100))
    img.paste((255, 0, 0), (0, 0, 50, 50))  # top-left: red
    img.paste((0, 255, 0), (50, 0, 100, 50))  # top-right: green
    img.paste((0, 0, 255), (0, 50, 50, 100))  # bottom-left: blue
    img.paste((255, 255, 0), (50, 50, 100, 100))  # bottom-right: yellow

    exif = Image.Exif()
    exif[0x0112] = orientation
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif)
    return buf.getvalue()


@pytest.mark.django_db
def test_profile_image_bakes_in_exif_orientation(user: User):
    """A profile image with EXIF orientation should be physically rotated on save."""
    raw = _make_oriented_image(orientation=6)  # 6 == rotate 90° clockwise to display

    # Reference: the pixels as they should look once orientation is applied.
    expected = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB")

    user.profile_image.save("photo.jpg", SimpleUploadedFile("photo.jpg", raw, "image/jpeg"))
    user.refresh_from_db()

    with user.profile_image.open("rb") as fh:
        processed = Image.open(fh).convert("RGB").resize((100, 100))

    # Top-left quadrant must match the oriented reference, not the raw (red) source.
    assert _dominant_color(processed, 25, 25) == _dominant_color(expected, 25, 25)
    assert _dominant_color(processed, 25, 25) != (255, 0, 0)


def _dominant_color(img: Image.Image, x: int, y: int) -> tuple[int, int, int]:
    """Snap a sampled pixel to pure primary channels to ignore compression noise."""
    r, g, b = img.getpixel((x, y))[:3]
    return (255 if r > 128 else 0, 255 if g > 128 else 0, 255 if b > 128 else 0)


@pytest.mark.django_db
class TestUserFixedPin:
    """Test the fixed PIN functionality on the User model."""

    def test_staff_user_cannot_enable_fixed_pin(self):
        """Test that staff users cannot enable fixed PIN."""
        user = UserFactory(is_staff=True)
        user.fixed_pin = "123456"
        user.fixed_pin_enabled = True

        with pytest.raises(ValidationError) as exc_info:
            user.full_clean()

        assert "Fixed PIN login is not allowed for staff users." in str(exc_info.value)

    def test_regular_user_can_enable_fixed_pin(self):
        """Test that regular users can enable fixed PIN."""
        user = UserFactory(is_staff=False)
        user.fixed_pin = "123456"
        user.fixed_pin_enabled = True

        # Should not raise any exception
        user.full_clean()
        user.save()

        assert user.fixed_pin == "123456"
        assert user.fixed_pin_enabled is True

    def test_superuser_cannot_enable_fixed_pin(self):
        """Test that superusers cannot enable fixed PIN."""
        user = UserFactory(is_superuser=True, is_staff=True)
        user.fixed_pin = "123456"
        user.fixed_pin_enabled = True

        with pytest.raises(ValidationError) as exc_info:
            user.full_clean()

        assert "Fixed PIN login is not allowed for staff users." in str(exc_info.value)

    def test_fixed_pin_defaults(self):
        """Test that fixed PIN fields have correct defaults."""
        user = UserFactory()

        assert user.fixed_pin == ""
        assert user.fixed_pin_enabled is False

    def test_fixed_pin_validation_in_login_pin_manager(self):
        """Test that LoginPin manager validates fixed PIN correctly."""
        user = UserFactory()
        user.fixed_pin = "123456"
        user.fixed_pin_enabled = True
        user.save()

        # Should validate fixed PIN when no regular PIN exists
        is_valid, reason = LoginPin.objects.validate_pin(user, "123456")
        assert is_valid is True
        assert reason is None

        # Should not validate wrong fixed PIN
        is_valid, reason = LoginPin.objects.validate_pin(user, "000000")
        assert is_valid is False
        assert reason == PinFailureReason.NO_PIN

    def test_fixed_pin_validation_when_disabled(self):
        """Test that fixed PIN validation fails when disabled."""
        user = UserFactory()
        user.fixed_pin = "123456"
        user.fixed_pin_enabled = False
        user.save()

        # Should not validate fixed PIN when disabled
        is_valid, reason = LoginPin.objects.validate_pin(user, "123456")
        assert is_valid is False
        assert reason == PinFailureReason.NO_PIN

    def test_fixed_pin_validation_with_empty_pin(self):
        """Test that fixed PIN validation fails with empty PIN."""
        user = UserFactory()
        user.fixed_pin = ""
        user.fixed_pin_enabled = True
        user.save()

        # Should not validate when PIN is empty
        is_valid, reason = LoginPin.objects.validate_pin(user, "123456")
        assert is_valid is False
        assert reason == PinFailureReason.NO_PIN

    def test_fixed_pin_as_fallback_with_regular_pin(self):
        """Test that fixed PIN works as fallback when regular PIN exists."""
        user = UserFactory()
        user.fixed_pin = "123456"
        user.fixed_pin_enabled = True
        user.save()

        # Create a regular PIN
        regular_pin = LoginPin.objects.generate_pin(user)

        # Regular PIN should work
        is_valid, reason = LoginPin.objects.validate_pin(user, regular_pin.pin)
        assert is_valid is True
        assert reason is None

        # Generate new regular PIN for next test
        regular_pin = LoginPin.objects.generate_pin(user)

        # Fixed PIN should work as fallback with wrong regular PIN
        is_valid, reason = LoginPin.objects.validate_pin(user, "123456")
        assert is_valid is True
        assert reason is None

    def test_fixed_pin_works_even_after_attempt_wipe(self):
        """The app-store-review fixed PIN keeps working after regular pins are locked out."""
        user = UserFactory()
        user.fixed_pin = "123456"
        user.fixed_pin_enabled = True
        user.save()

        pin = LoginPin.objects.generate_pin(user)
        LoginPin.objects.filter(pk=pin.pk).update(failed_attempts=LoginPin.MAX_ATTEMPTS)

        is_valid, reason = LoginPin.objects.validate_pin(user, "123456")
        assert is_valid is True
        assert reason is None


def _wrong_pin(*pins: LoginPin) -> str:
    """A 6-digit code that matches none of the given pins."""
    taken = {p.pin for p in pins}
    return next(c for c in ("000000", "000001", "000002", "000003") if c not in taken)


@pytest.mark.django_db
class TestLoginPinMultiPin:
    """Up to MAX_ACTIVE_PINS codes are valid at once; attempts are summed across them."""

    def test_resent_code_keeps_older_codes_working(self):
        # Regression: a user who requests a code twice (double click, resend) must
        # be able to log in with the code from the *first* email.
        user = UserFactory()
        first = LoginPin.objects.generate_pin(user)
        LoginPin.objects.generate_pin(user)

        is_valid, reason = LoginPin.objects.validate_pin(user, first.pin)
        assert is_valid is True
        assert reason is None

    def test_at_most_three_active_pins(self):
        user = UserFactory()
        pins = [LoginPin.objects.generate_pin(user) for _ in range(4)]

        remaining = set(LoginPin.objects.filter(user=user).values_list("pk", flat=True))
        assert remaining == {p.pk for p in pins[1:]}

    def test_generate_pin_purges_expired_pins(self):
        user = UserFactory()
        old = LoginPin.objects.generate_pin(user)
        LoginPin.objects.filter(pk=old.pk).update(expires_at=timezone.now() - timedelta(minutes=1))

        new = LoginPin.objects.generate_pin(user)
        assert list(LoginPin.objects.filter(user=user).values_list("pk", flat=True)) == [new.pk]

    def test_success_consumes_all_pins(self):
        user = UserFactory()
        LoginPin.objects.generate_pin(user)
        pin = LoginPin.objects.generate_pin(user)

        is_valid, reason = LoginPin.objects.validate_pin(user, pin.pin)
        assert is_valid is True
        assert reason is None
        assert not LoginPin.objects.filter(user=user).exists()

        # Replaying the consumed code fails
        is_valid, reason = LoginPin.objects.validate_pin(user, pin.pin)
        assert is_valid is False
        assert reason == PinFailureReason.NO_PIN

    def test_mismatch_increments_newest_pin_only(self):
        user = UserFactory()
        older = LoginPin.objects.generate_pin(user)
        newest = LoginPin.objects.generate_pin(user)

        is_valid, reason = LoginPin.objects.validate_pin(user, _wrong_pin(older, newest))
        assert is_valid is False
        assert reason == PinFailureReason.MISMATCH

        older.refresh_from_db()
        newest.refresh_from_db()
        assert older.failed_attempts == 0
        assert newest.failed_attempts == 1

    def test_attempts_summed_across_pins_wipe_all(self):
        user = UserFactory()
        p1 = LoginPin.objects.generate_pin(user)
        p2 = LoginPin.objects.generate_pin(user)
        LoginPin.objects.filter(pk=p1.pk).update(failed_attempts=6)
        LoginPin.objects.filter(pk=p2.pk).update(failed_attempts=4)

        # Even the correct code is rejected once the summed attempts hit the cap,
        # and every pin is invalidated.
        is_valid, reason = LoginPin.objects.validate_pin(user, p2.pin)
        assert is_valid is False
        assert reason == PinFailureReason.TOO_MANY_ATTEMPTS
        assert not LoginPin.objects.filter(user=user).exists()

    def test_expired_pin_reason(self):
        user = UserFactory()
        pin = LoginPin.objects.generate_pin(user)
        LoginPin.objects.filter(pk=pin.pk).update(expires_at=timezone.now() - timedelta(minutes=1))

        is_valid, reason = LoginPin.objects.validate_pin(user, pin.pin)
        assert is_valid is False
        assert reason == PinFailureReason.EXPIRED

    def test_no_pin_reason(self):
        user = UserFactory()
        is_valid, reason = LoginPin.objects.validate_pin(user, "123456")
        assert is_valid is False
        assert reason == PinFailureReason.NO_PIN

    def test_cleanup_removes_only_expired_pins(self):
        user = UserFactory()
        keep = LoginPin.objects.generate_pin(user)
        gone = LoginPin.objects.generate_pin(user)
        LoginPin.objects.filter(pk=gone.pk).update(expires_at=timezone.now() - timedelta(minutes=1))

        LoginPin.cleanup()
        assert list(LoginPin.objects.filter(user=user).values_list("pk", flat=True)) == [keep.pk]


@pytest.mark.django_db
class TestCircleCount:
    def test_uses_prefetched_sessions(self, django_assert_num_queries):
        from totem.spaces.tests.factories import SessionFactory

        user = UserFactory()
        for _ in range(3):
            SessionFactory().joined.add(user)

        fetched = User.objects.prefetch_related("sessions_joined").get(pk=user.pk)
        with django_assert_num_queries(0):
            assert fetched.circle_count == 3

        plain = User.objects.get(pk=user.pk)
        with django_assert_num_queries(1):
            assert plain.circle_count == 3
