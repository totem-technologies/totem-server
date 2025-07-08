import pytest
from django.core.exceptions import ValidationError

from totem.users.models import User, LoginPin
from totem.users.tests.factories import UserFactory


def test_user_get_absolute_url(user: User):
    assert user.get_absolute_url() == f"/users/u/{user.slug}/"


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
