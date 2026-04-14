from unittest.mock import patch

import pytest
from django.test import Client
from oauth2_provider.models import Application
from pytest_socket import disable_socket

from totem.api.oauth import create_oauth_tokens
from totem.users.models import User
from totem.users.tests.factories import UserFactory


@pytest.fixture(autouse=True)
def media_storage(settings, tmpdir):
    settings.MEDIA_ROOT = tmpdir.strpath


@pytest.fixture
def user(db) -> User:
    return UserFactory()


@pytest.fixture
def proxied_site_mock(request):
    mock_content = "<h1>Proxied Site Page</h1>"
    patched = patch("totem.pages.views.get_proxied_site_page", return_value=mock_content)
    mock = patched.__enter__()

    def unpatch():
        # Make sure the mock was actually called
        assert mock.called, "The proxied site mock was not called"
        patched.__exit__(None, None, None)

    request.addfinalizer(unpatch)


@pytest.fixture
def oauth_app(db) -> Application:
    """Get or create the Totem Mobile OAuth application for tests."""
    app, _ = Application.objects.get_or_create(
        name="Totem Mobile",
        defaults={
            "client_type": Application.CLIENT_PUBLIC,
            "authorization_grant_type": Application.GRANT_PASSWORD,
            "skip_authorization": True,
        },
    )
    return app


# API fixtures
@pytest.fixture
def auth_user(oauth_app):
    """Create a user for testing authentication."""
    return UserFactory(email="auth_test@example.com")


@pytest.fixture
def auth_token(auth_user):
    """Generate a valid OAuth access token for the test user."""
    tokens = create_oauth_tokens(auth_user)
    return tokens.access_token


@pytest.fixture
def client_with_user(oauth_app):
    """Create a user with a valid OAuth access token."""
    user = UserFactory()
    tokens = create_oauth_tokens(user)
    return Client(HTTP_AUTHORIZATION=f"Bearer {tokens.access_token}"), user


def pytest_runtest_setup():
    disable_socket()
