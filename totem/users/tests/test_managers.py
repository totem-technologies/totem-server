from io import StringIO

import pytest
from django.core.management import call_command

from totem.users.models import User


@pytest.mark.django_db
class TestUserManager:
    def test_create_user(self):
        user = User.objects.create_user(
            email="JOHN@totem.ORG",
        )
        assert user.email == "john@totem.org"
        assert not user.is_staff
        assert not user.is_superuser
        assert not user.has_usable_password()
        assert user.username is None

    def test_create_superuser(self):
        user = User.objects.create_superuser(
            email="admin@totem.org",
        )
        assert user.email == "admin@totem.org"
        assert user.is_staff
        assert user.is_superuser
        assert not user.has_usable_password()
        assert user.username is None

    def test_create_superuser_username_ignored(self):
        user = User.objects.create_superuser(
            email="test@totem.org",
        )
        assert user.username is None

    def test_get_or_create_sets_unusable_password(self):
        user: User
        user, created = User.objects.get_or_create(email="new@TOTEM.org")
        assert user.email == "new@totem.org"
        assert created
        assert not user.has_usable_password()

    def test_get_or_create_existing_user(self):
        User.objects.create_user(email="existing@totem.org")
        user: User
        user, created = User.objects.get_or_create(email="existing@totem.ORG")
        assert not created
        assert not user.has_usable_password()


@pytest.mark.django_db
def test_createsuperuser_command():
    """Ensure createsuperuser command works with our custom manager."""
    out = StringIO()
    command_result = call_command(
        "createsuperuser",
        "--email",
        "henry@totem.org",
        interactive=False,
        stdout=out,
    )

    assert command_result is None
    assert out.getvalue() == "Superuser created successfully.\n"
    user = User.objects.get(email="henry@totem.org")
    assert not user.has_usable_password()
