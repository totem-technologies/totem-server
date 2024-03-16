from unittest.mock import patch

import pytest
from pytest_socket import disable_socket

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


def pytest_runtest_setup():
    disable_socket()
