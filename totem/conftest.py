from unittest.mock import patch

import pytest
from django.test import Client
from pytest_socket import disable_socket

from totem.api.auth import generate_jwt_token
from totem.users.models import User
from totem.users.tests.factories import UserFactory


@pytest.fixture(autouse=True)
def media_storage(settings, tmpdir):
    settings.MEDIA_ROOT = tmpdir.strpath


@pytest.fixture
def user(db) -> User:
    return UserFactory()


@pytest.fixture
def webflow_mock(request):
    mock_content = "<h1>Webflow Page</h1>"
    patched = patch("totem.pages.webflow.get", return_value=mock_content)
    mock = patched.__enter__()

    def unpatch():
        # Make sure the mock was actually called
        assert mock.called, "The webflow mock was not called"
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


def pytest_runtest_setup():
    disable_socket()
