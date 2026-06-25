import io

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image, ImageOps

from totem.users.models import LoginPin, User
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
        is_valid, pin_obj = LoginPin.objects.validate_pin(user, "123456")
        assert is_valid is True
        assert pin_obj is None

        # Should not validate wrong fixed PIN
        is_valid, pin_obj = LoginPin.objects.validate_pin(user, "000000")
        assert is_valid is False
        assert pin_obj is None

    def test_fixed_pin_validation_when_disabled(self):
        """Test that fixed PIN validation fails when disabled."""
        user = UserFactory()
        user.fixed_pin = "123456"
        user.fixed_pin_enabled = False
        user.save()

        # Should not validate fixed PIN when disabled
        is_valid, pin_obj = LoginPin.objects.validate_pin(user, "123456")
        assert is_valid is False
        assert pin_obj is None

    def test_fixed_pin_validation_with_empty_pin(self):
        """Test that fixed PIN validation fails with empty PIN."""
        user = UserFactory()
        user.fixed_pin = ""
        user.fixed_pin_enabled = True
        user.save()

        # Should not validate when PIN is empty
        is_valid, pin_obj = LoginPin.objects.validate_pin(user, "123456")
        assert is_valid is False
        assert pin_obj is None

    def test_fixed_pin_as_fallback_with_regular_pin(self):
        """Test that fixed PIN works as fallback when regular PIN exists."""
        user = UserFactory()
        user.fixed_pin = "123456"
        user.fixed_pin_enabled = True
        user.save()

        # Create a regular PIN
        regular_pin = LoginPin.objects.generate_pin(user)

        # Regular PIN should work
        is_valid, pin_obj = LoginPin.objects.validate_pin(user, regular_pin.pin)
        assert is_valid is True
        assert pin_obj is not None

        # Generate new regular PIN for next test
        regular_pin = LoginPin.objects.generate_pin(user)

        # Fixed PIN should work as fallback with wrong regular PIN
        is_valid, pin_obj = LoginPin.objects.validate_pin(user, "123456")
        assert is_valid is True
        assert pin_obj is None
