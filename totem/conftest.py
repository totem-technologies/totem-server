from unittest.mock import patch

import pytest
import requests
from django.test import Client

from totem.api.auth import generate_jwt_token
from totem.users.models import User
from totem.users.tests.factories import UserFactory


def fake_upstream(status: int, body: bytes = b"", content_type: str = "text/plain") -> requests.Response:
    """A canned requests.Response for tests that mock a proxied upstream."""
    r = requests.Response()
    r.status_code = status
    r._content = body
    r.headers["Content-Type"] = content_type
    r.raw = type("R", (), {"stream": lambda self, *a, **kw: iter([body])})()
    return r


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


# API fixtures
@pytest.fixture
def auth_user():
    """Create a user for testing authentication."""
    return UserFactory(email="auth_test@example.com")


@pytest.fixture
def auth_token(auth_user):
    """Generate a valid auth token for the test user."""
    return generate_jwt_token(auth_user)


@pytest.fixture
def client_with_user():
    """Generate a valid auth token for the test user."""
    user = UserFactory()
    token = generate_jwt_token(user)
    return Client(HTTP_AUTHORIZATION=f"Bearer {token}"), user
